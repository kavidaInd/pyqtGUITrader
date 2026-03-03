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
  - FEATURE 3: Confidence scores for current signal

Embed in TradingGUI as a pinned sidebar OR show as a floating popup.

UPDATED: Now uses state_manager instead of direct trading_app.state access.
FULLY INTEGRATED with ThemeManager for dynamic theming.

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
    QGridLayout, QProgressBar, QGroupBox
)

from strategy.strategy_manager import strategy_manager

# Import state manager
from data.trade_state_manager import state_manager

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Import SIGNAL_GROUPS as strings from the right place
# These are the string values used in the engine config
SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

SIGNAL_LABELS = {
    "BUY_CALL": "📈 Buy Call",
    "BUY_PUT": "📉 Buy Put",
    "EXIT_CALL": "🔴 Exit Call",
    "EXIT_PUT": "🟠 Exit Put",
    "HOLD": "⏸ Hold",
    "WAIT": "⏳ Wait",
}


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


def get_signal_colors():
    """Get signal colors from theme manager."""
    c = theme_manager.palette
    return {
        "BUY_CALL": c.GREEN,
        "BUY_PUT": c.BLUE,
        "EXIT_CALL": c.RED,
        "EXIT_PUT": c.ORANGE,
        "HOLD": c.YELLOW,
        "WAIT": c.TEXT_DISABLED,
    }


def _ss() -> str:
    """Generate stylesheet with current theme tokens."""
    c = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    return f"""
        QDialog, QWidget {{
            background: {c.BG_MAIN}; color: {c.TEXT_MAIN}; font-size: {ty.SIZE_BODY}pt;
        }}
        QLabel {{ color: {c.TEXT_MAIN}; }}
        QGroupBox {{
            background: {c.BG_PANEL};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_MD}px;
            margin-top: {sp.PAD_MD}px;
            font-weight: {ty.WEIGHT_BOLD};
            color: {c.TEXT_MAIN};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {sp.PAD_MD}px;
            padding: 0 {sp.PAD_XS}px;
            color: {c.BLUE};
        }}
        QProgressBar {{
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            background: {c.BG_PANEL};
            text-align: center;
            color: {c.TEXT_MAIN};
            font-size: {ty.SIZE_XS}pt;
            min-height: {sp.PROGRESS_SM}px;
            max-height: {sp.PROGRESS_MD}px;
        }}
        QProgressBar::chunk {{
            background: {c.BLUE};
            border-radius: {sp.RADIUS_SM}px;
        }}
        QPushButton {{
            background: {c.BG_HOVER}; color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER}; border-radius: {sp.RADIUS_MD}px;
            padding: {sp.PAD_XS}px {sp.PAD_MD}px; font-size: {ty.SIZE_BODY}pt; font-weight: {ty.WEIGHT_BOLD};
        }}
        QPushButton:hover {{ background: {c.BORDER}; }}
        QPushButton:disabled {{ background: {c.BG_PANEL}; color: {c.TEXT_DISABLED}; }}
        QListWidget {{
            background: {c.BG_PANEL}; color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER}; border-radius: {sp.RADIUS_SM}px;
            font-size: {ty.SIZE_BODY}pt; outline: none;
        }}
        QListWidget::item {{
            padding: {sp.PAD_MD}px {sp.PAD_MD}px;
            border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
        }}
        QListWidget::item:selected {{
            background: {c.BG_SELECTED}; color: {c.BLUE};
            border-left: {sp.PAD_XS}px solid {c.BLUE};
        }}
        QListWidget::item:hover {{ background: {c.BG_HOVER}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QFrame {{ background: transparent; }}
    """


class _ConfidenceBar(QWidget, ThemedMixin):
    """FEATURE 3: Confidence bar for signal groups"""

    def __init__(self, signal: str, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.signal = signal

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_XS)

            self.label = QLabel(SIGNAL_LABELS.get(signal, signal))
            self.label.setFixedWidth(80)
            layout.addWidget(self.label)

            self.progress = QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFixedHeight(self._sp.PROGRESS_MD)
            self.progress.setTextVisible(False)
            layout.addWidget(self.progress, 1)

            self.value = QLabel("0%")
            self.value.setFixedWidth(40)
            layout.addWidget(self.value)

            self.apply_theme()
        except Exception as e:
            logger.error(f"[_ConfidenceBar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.signal = ""
        self.label = None
        self.progress = None
        self.value = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the confidence bar."""
        try:
            c = self._c
            ty = self._ty

            if self.label:
                self.label.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt;")

            if self.value:
                self.value.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")
        except Exception as e:
            logger.error(f"[_ConfidenceBar.apply_theme] Failed: {e}", exc_info=True)

    def set_confidence(self, confidence: float, threshold: float = 0.6):
        """Set confidence value"""
        try:
            c = self._c
            sp = self._sp

            percent = int(confidence * 100)
            self.progress.setValue(percent)
            self.value.setText(f"{percent}%")

            # Color based on threshold
            if confidence >= threshold:
                color = c.GREEN
            elif confidence >= threshold * 0.7:
                color = c.YELLOW
            else:
                color = c.RED

            self.progress.setStyleSheet(f"""
                QProgressBar::chunk {{ background: {color}; border-radius: {sp.RADIUS_SM}px; }}
                QProgressBar {{ border: {sp.SEPARATOR}px solid {c.BORDER}; border-radius: {sp.RADIUS_SM}px; background: {c.BG_PANEL}; }}
            """)
        except Exception as e:
            logger.error(f"[_ConfidenceBar.set_confidence] Failed: {e}", exc_info=True)


class _StrategyCard(QFrame, ThemedMixin):
    """Expanded card showing active strategy details."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QVBoxLayout(self)
            # Margins and spacing will be set in apply_theme

            header = QHBoxLayout()
            self._badge = QLabel("⚡ ACTIVE")
            header.addWidget(self._badge)
            header.addStretch()
            self._signal_lbl = QLabel()
            header.addWidget(self._signal_lbl)
            layout.addLayout(header)

            self._name_lbl = QLabel("—")
            layout.addWidget(self._name_lbl)

            self._desc_lbl = QLabel()
            self._desc_lbl.setWordWrap(True)
            layout.addWidget(self._desc_lbl)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            layout.addWidget(sep)

            # Stats row
            stats = QHBoxLayout()
            self._rules_lbl = self._stat_lbl("0 rules")
            self._updated_lbl = self._stat_lbl("—")
            stats.addWidget(self._rules_lbl)
            stats.addStretch()
            stats.addWidget(self._updated_lbl)
            layout.addLayout(stats)

            # FEATURE 3: Confidence threshold display
            self._threshold_lbl = QLabel("Threshold: 60%")
            layout.addWidget(self._threshold_lbl)

            self.apply_theme()

        except Exception as e:
            logger.error(f"[_StrategyCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._badge = None
        self._signal_lbl = None
        self._name_lbl = None
        self._desc_lbl = None
        self._rules_lbl = None
        self._updated_lbl = None
        self._threshold_lbl = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the card."""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Update card style
            self.setStyleSheet(f"""
                QFrame {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                }}
            """)

            layout = self.layout()
            if layout:
                layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
                layout.setSpacing(sp.GAP_XS)

            if self._badge:
                self._badge.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_XS}pt; font-weight:{ty.WEIGHT_BOLD};")

            # Signal label will be updated in update() method

            if self._name_lbl:
                self._name_lbl.setStyleSheet(f"color:{c.TEXT_MAIN}; font-size:{ty.SIZE_BODY}pt; font-weight:{ty.WEIGHT_BOLD};")

            if self._desc_lbl:
                self._desc_lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")

            if sep := self.findChild(QFrame, "separator"):
                sep.setStyleSheet(f"QFrame{{background:{c.BORDER};max-height:{sp.SEPARATOR}px;border:none;}}")

            if self._threshold_lbl:
                self._threshold_lbl.setStyleSheet(f"color:{c.YELLOW}; font-size:{ty.SIZE_XS}pt; font-weight:{ty.WEIGHT_BOLD};")

        except Exception as e:
            logger.error(f"[_StrategyCard.apply_theme] Failed: {e}", exc_info=True)

    def _stat_lbl(self, text: str) -> QLabel:
        try:
            c = self._c
            ty = self._ty
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            return lbl
        except Exception as e:
            logger.error(f"[_StrategyCard._stat_lbl] Failed: {e}", exc_info=True)
            return QLabel(text)

    def update(self, strategy: Dict, current_signal: str = "WAIT", threshold: float = 0.6):
        """Update card with strategy data and current signal"""
        try:
            c = self._c
            signal_colors = get_signal_colors()

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

            # FEATURE 3: Update threshold
            if self._threshold_lbl:
                threshold_pct = int(threshold * 100)
                self._threshold_lbl.setText(f"Min Confidence: {threshold_pct}%")

            # Signal
            color = signal_colors.get(current_signal, c.TEXT_DISABLED)
            label = SIGNAL_LABELS.get(current_signal, current_signal)
            if self._signal_lbl:
                self._signal_lbl.setText(label)
                self._signal_lbl.setStyleSheet(
                    f"color:{color}; font-size:{self._ty.SIZE_XS}pt; font-weight:{self._ty.WEIGHT_BOLD};"
                    f" background:{color}22; border:{self._sp.SEPARATOR}px solid {color}55;"
                    f" border-radius:{self._sp.RADIUS_SM}px; padding:{self._sp.PAD_XS}px {self._sp.PAD_SM}px;"
                )
        except Exception as e:
            logger.error(f"[_StrategyCard.update] Failed: {e}", exc_info=True)


class StrategyPickerSidebar(QDialog, ThemedMixin):
    """
    Compact floating sidebar for switching active strategy.
    Non-modal — can stay open while trading. Uses database-backed strategy manager.

    FEATURE 3: Displays confidence scores for signal groups.
    UPDATED: Now uses state_manager for signal data.
    FULLY INTEGRATED with ThemeManager for dynamic theming.
    """
    strategy_activated = pyqtSignal(str)  # emitted with slug
    open_editor_requested = pyqtSignal()  # user wants full editor

    def __init__(self, trading_app=None, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, Qt.Window | Qt.Tool)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.trading_app = trading_app
            self._current_signal = "WAIT"
            self._current_threshold = 0.6
            self._confidence_bars = {}

            # Cache for snapshots
            self._last_snapshot = {}
            self._last_snapshot_time = None
            self._snapshot_cache_duration = 0.1  # 100ms

            self.setWindowTitle("⚡ Strategy Picker")
            self.setFixedWidth(400)  # Slightly wider for confidence bars
            self.setMinimumHeight(600)
            self.setMaximumHeight(900)

            self._build_ui()
            self.refresh()
            self.apply_theme()

            # Auto-refresh signal display every 2s
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_data)
            self._timer.start(2000)

            logger.info("StrategyPickerSidebar (database) initialized with Feature 3 and state_manager")

        except Exception as e:
            logger.critical(f"[StrategyPickerSidebar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent, Qt.Window | Qt.Tool)
            self.setWindowTitle("Strategy Picker - ERROR")
            self.setMinimumWidth(300)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL, self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel(f"Failed to initialize strategy picker:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self._current_signal = "WAIT"
        self._current_threshold = 0.6
        self._confidence_bars = {}
        self._timer = None
        self._card = None
        self._list = None
        self._activate_btn = None
        self._status_lbl = None
        self._confidence_group = None
        self._last_snapshot = {}
        self._last_snapshot_time = None
        self._snapshot_cache_duration = 0.1

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the sidebar.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            # Apply main stylesheet
            self.setStyleSheet(_ss())

            # Update activate button
            if self._activate_btn:
                self._activate_btn.setStyleSheet(
                    f"QPushButton{{background:{c.BLUE_DARK};color:{c.TEXT_INVERSE};border:{sp.SEPARATOR}px solid {c.BLUE};"
                    f"border-radius:{sp.RADIUS_MD}px;padding:{sp.PAD_SM}px;font-weight:{ty.WEIGHT_BOLD};font-size:{ty.SIZE_BODY}pt;}}"
                    f"QPushButton:hover{{background:{c.BLUE};}}"
                )

            # Update status label
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.GREEN}; font-size:{ty.SIZE_XS}pt;")

            # Update card
            if self._card and hasattr(self._card, 'apply_theme'):
                self._card.apply_theme()

            # Update confidence bars
            for bar in self._confidence_bars.values():
                if hasattr(bar, 'apply_theme'):
                    bar.apply_theme()

            # Refresh list items to update colors
            self._refresh_list_colors()

            logger.debug("[StrategyPickerSidebar.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar.apply_theme] Failed: {e}", exc_info=True)

    def _refresh_list_colors(self):
        """Refresh colors in the strategy list"""
        try:
            c = self._c
            active_slug = strategy_manager.get_active_slug()

            for i in range(self._list.count()):
                item = self._list.item(i)
                slug = item.data(Qt.UserRole)
                if slug == active_slug:
                    item.setForeground(QColor(c.BLUE))
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setForeground(QColor(c.TEXT_MAIN))
                    font = QFont()
                    font.setBold(False)
                    item.setFont(font)
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._refresh_list_colors] Failed: {e}", exc_info=True)

    def _get_cached_snapshot(self) -> Dict[str, Any]:
        """Get cached snapshot to avoid excessive state_manager calls"""
        from datetime import datetime
        now = datetime.now()
        if (self._last_snapshot_time is None or
            (now - self._last_snapshot_time).total_seconds() > self._snapshot_cache_duration):
            self._last_snapshot = state_manager.get_snapshot()
            self._last_snapshot_time = now
        return self._last_snapshot

    def _build_ui(self):
        """Build the UI components"""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            root = QVBoxLayout(self)
            root.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
            root.setSpacing(sp.GAP_SM)

            # Active strategy card
            self._card = _StrategyCard()
            root.addWidget(self._card)

            # FEATURE 3: Confidence scores group
            self._confidence_group = QGroupBox("Signal Confidence")
            confidence_layout = QVBoxLayout(self._confidence_group)
            confidence_layout.setSpacing(sp.GAP_XS)

            # Create confidence bars for each signal group
            signal_groups = ['BUY_CALL', 'BUY_PUT', 'EXIT_CALL', 'EXIT_PUT', 'HOLD']
            for signal in signal_groups:
                bar = _ConfidenceBar(signal)
                confidence_layout.addWidget(bar)
                self._confidence_bars[signal] = bar

            root.addWidget(self._confidence_group)

            # ── Separator ─────────────────────────────────────────────────────────
            sep = QLabel("  ALL STRATEGIES")
            sep.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt; font-weight:{ty.WEIGHT_BOLD}; padding:{sp.PAD_XS}px 0 {sp.PAD_XS}px 0;")
            root.addWidget(sep)

            # Strategy list
            self._list = QListWidget()
            self._list.setSelectionMode(QAbstractItemView.SingleSelection)
            self._list.itemDoubleClicked.connect(self._on_double_click)
            root.addWidget(self._list, 1)

            # ── Activate button ───────────────────────────────────────────────────
            self._activate_btn = QPushButton("⚡ Activate Selected")
            self._activate_btn.clicked.connect(self._on_activate)
            root.addWidget(self._activate_btn)

            # ── Footer ────────────────────────────────────────────────────────────
            foot = QHBoxLayout()
            foot.setSpacing(sp.GAP_SM)

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

            c = self._c
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

                    # FEATURE 3: Add confidence info to tooltip
                    if is_active:
                        tooltip += f"\nMin confidence: {engine.get('min_confidence', 0.6)*100:.0f}%"

                    item.setToolTip(tooltip)

                    if is_active:
                        item.setForeground(QColor(c.BLUE))
                        font = QFont()
                        font.setBold(True)
                        item.setFont(font)

                    self._list.addItem(item)

                except Exception as e:
                    logger.warning(f"Failed to add strategy item: {e}")
                    continue

            self._list.blockSignals(False)

            # Update active card and confidence bars
            self._update_active_display()

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar.refresh] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def _refresh_data(self):
        """Pull current data from state_manager and update UI."""
        try:
            if not self.isVisible():
                return

            self._update_active_display()

        except Exception as e:
            logger.debug(f"[_refresh_data] Failed: {e}")

    def _update_active_display(self):
        """Update active strategy card and confidence bars using state_manager"""
        try:
            c = self._c

            # Get snapshots from state manager
            snapshot = self._get_cached_snapshot()
            position_snapshot = state_manager.get_position_snapshot()

            # Get signal from position snapshot
            signal_value = position_snapshot.get('option_signal', 'WAIT')

            # Get signal snapshot for confidence
            try:
                signal_snap = state_manager.get_state().get_option_signal_snapshot()
                confidence = signal_snap.get('confidence', {})
                threshold = signal_snap.get('threshold', 0.6)
            except Exception:
                confidence = {}
                threshold = 0.6

            # Update active strategy
            active = strategy_manager.get_active()
            if active is not None:
                engine = active.get("engine", {})
                threshold = engine.get("min_confidence", 0.6)

                if self._card is not None:
                    self._card.update(active, signal_value, threshold)

                # Update confidence bars
                for signal, bar in self._confidence_bars.items():
                    conf = confidence.get(signal, 0.0)
                    bar.set_confidence(conf, threshold)

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._update_active_display] Failed: {e}", exc_info=True)

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
            c = self._c
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
                    self._status_lbl.setStyleSheet(f"color:{c.GREEN}; font-size:{self._ty.SIZE_XS}pt;")
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
            self._confidence_group = None
            self._confidence_bars.clear()
            self._last_snapshot = {}
            self._last_snapshot_time = None

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