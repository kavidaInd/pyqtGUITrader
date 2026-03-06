"""
strategy_picker_sidebar_db.py
==============================
A compact, non-modal sidebar popup for quickly switching the active strategy
at runtime without opening the full editor. Uses database-backed strategy manager.

MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
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
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QMetaObject, Q_ARG
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
    QGridLayout, QProgressBar, QGroupBox
)

from Utils.safe_getattr import safe_hasattr
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


class ModernCard(QFrame):
    """Modern card widget with consistent styling."""

    def __init__(self, parent=None, elevated=False):
        super().__init__(parent)
        self.setObjectName("modernCard")
        self.elevated = elevated
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing

        base_style = f"""
            QFrame#modernCard {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                padding: {sp.PAD_LG}px;
            }}
        """

        if self.elevated:
            base_style += f"""
                QFrame#modernCard {{
                    border: 1px solid {c.BORDER_FOCUS};
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                               stop:0 {c.BG_PANEL}, stop:1 {c.BG_HOVER});
                }}
            """

        self.setStyleSheet(base_style)


class StatusBadge(QLabel):
    """Status badge with color-coded background."""
    
    def __init__(self, text="", status="neutral"):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(60)
        self.set_status(status)
    
    def set_status(self, status):
        """Update badge color based on status."""
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography
        
        if status == "success":
            color = c.GREEN
            bg = c.GREEN + "20"
        elif status == "warning":
            color = c.ORANGE
            bg = c.ORANGE + "20"
        elif status == "error":
            color = c.RED
            bg = c.RED + "20"
        elif status == "info":
            color = c.BLUE
            bg = c.BLUE + "20"
        else:
            color = c.TEXT_DIM
            bg = c.BG_HOVER
        
        self.setStyleSheet(f"""
            QLabel#statusBadge {{
                color: {color};
                background: {bg};
                border: 1px solid {color};
                border-radius: {sp.RADIUS_PILL}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)


class ValueLabel(QLabel):
    """Value label with consistent styling."""
    
    def __init__(self, text="--", parent=None):
        super().__init__(text, parent)
        self.setObjectName("valueLabel")
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setMinimumWidth(40)
        self._apply_style()
    
    def _apply_style(self):
        c = theme_manager.palette
        sp = theme_manager.spacing
        ty = theme_manager.typography
        
        self.setStyleSheet(f"""
            QLabel#valueLabel {{
                color: {c.TEXT_MAIN};
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
        """)


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


class _ConfidenceBar(QWidget, ThemedMixin):
    """FEATURE 3: Confidence bar for signal groups with modern design"""

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
            layout.setSpacing(self._sp.GAP_MD)

            # Signal label
            self.label = QLabel(SIGNAL_LABELS.get(signal, signal))
            self.label.setFixedWidth(90)
            self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(self.label)

            # Progress bar
            self.progress = QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFixedHeight(self._sp.PROGRESS_SM)
            self.progress.setTextVisible(False)
            layout.addWidget(self.progress, 1)

            # Percentage value
            self.value = ValueLabel("0%")
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
                QProgressBar {{
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    background: {c.BG_HOVER};
                    text-align: center;
                }}
                QProgressBar::chunk {{
                    background: {color};
                    border-radius: {sp.RADIUS_SM}px;
                }}
            """)
        except Exception as e:
            logger.error(f"[_ConfidenceBar.set_confidence] Failed: {e}", exc_info=True)


class _StrategyCard(ModernCard, ThemedMixin):
    """Expanded card showing active strategy details with modern design."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD,
                                     self._sp.PAD_MD, self._sp.PAD_MD)
            layout.setSpacing(self._sp.GAP_MD)

            # Header with badge and signal
            header = QHBoxLayout()
            self._badge = StatusBadge("ACTIVE", "success")
            header.addWidget(self._badge)
            header.addStretch()

            self._signal_badge = StatusBadge("WAIT", "neutral")
            header.addWidget(self._signal_badge)
            layout.addLayout(header)

            # Strategy name
            self._name_lbl = QLabel("—")
            self._name_lbl.setStyleSheet(f"""
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_LG}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            """)
            layout.addWidget(self._name_lbl)

            # Description
            self._desc_lbl = QLabel()
            self._desc_lbl.setWordWrap(True)
            self._desc_lbl.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_SM}pt;")
            layout.addWidget(self._desc_lbl)

            # Separator
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"background: {self._c.BORDER}; max-height: 1px;")
            layout.addWidget(sep)

            # Stats row
            stats = QHBoxLayout()
            self._rules_badge = StatusBadge("0 rules", "neutral")
            stats.addWidget(self._rules_badge)

            stats.addStretch()

            self._updated_lbl = QLabel("—")
            self._updated_lbl.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            stats.addWidget(self._updated_lbl)
            layout.addLayout(stats)

            # FEATURE 3: Confidence threshold display
            threshold_layout = QHBoxLayout()
            threshold_layout.addWidget(QLabel("Min Confidence:"))
            self._threshold_lbl = ValueLabel("60%")
            threshold_layout.addWidget(self._threshold_lbl)
            threshold_layout.addStretch()
            layout.addLayout(threshold_layout)

            self.apply_theme()

        except Exception as e:
            logger.error(f"[_StrategyCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._badge = None
        self._signal_badge = None
        self._name_lbl = None
        self._desc_lbl = None
        self._rules_badge = None
        self._updated_lbl = None
        self._threshold_lbl = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the card."""
        try:
            c = self._c
            sp = self._sp

            # Call parent apply_theme to update card styling
            super()._apply_style()

            # Update specific children
            if self._name_lbl:
                self._name_lbl.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {self._ty.SIZE_LG}pt; font-weight: {self._ty.WEIGHT_BOLD};")

            if self._desc_lbl:
                self._desc_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {self._ty.SIZE_SM}pt;")

            if self._updated_lbl:
                self._updated_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

        except Exception as e:
            logger.error(f"[_StrategyCard.apply_theme] Failed: {e}", exc_info=True)

    def update(self, strategy: Dict, current_signal: str = "WAIT", threshold: float = 0.6):
        """Update card with strategy data and current signal"""
        try:
            c = self._c
            signal_colors = get_signal_colors()

            if strategy is None:
                logger.warning("update called with None strategy")
                return

            # Strategy name
            if self._name_lbl:
                self._name_lbl.setText(str(strategy.get("name", "—")))

            # Description
            desc = strategy.get("description", "")
            if self._desc_lbl:
                self._desc_lbl.setText(desc[:100] + ("…" if len(desc) > 100 else ""))
                self._desc_lbl.setVisible(bool(desc))

            # Rules count
            engine = strategy.get("engine", {})
            total = 0
            for sig in SIGNAL_GROUPS:
                group = engine.get(sig, {}) if engine else {}
                rules = group.get("rules", []) if isinstance(group, dict) else []
                total += len(rules)

            if self._rules_badge:
                self._rules_badge.setText(f"{total} rule{'s' if total != 1 else ''}")
                self._rules_badge.set_status("info" if total > 0 else "neutral")

            # Updated timestamp
            upd = strategy.get("updated_at", "—")
            if upd and "T" in upd:
                upd = upd.replace("T", " ")[:16]
            if self._updated_lbl:
                self._updated_lbl.setText(f"Updated: {upd}")

            # FEATURE 3: Update threshold
            if self._threshold_lbl:
                threshold_pct = int(threshold * 100)
                self._threshold_lbl.setText(f"{threshold_pct}%")

            # Signal badge
            color = signal_colors.get(current_signal, c.TEXT_DISABLED)
            label = SIGNAL_LABELS.get(current_signal, current_signal)
            if self._signal_badge:
                self._signal_badge.setText(label)
                if current_signal in ["BUY_CALL", "BUY_PUT", "HOLD"]:
                    self._signal_badge.set_status("success")
                elif current_signal in ["EXIT_CALL", "EXIT_PUT"]:
                    self._signal_badge.set_status("warning")
                else:
                    self._signal_badge.set_status("neutral")

        except Exception as e:
            logger.error(f"[_StrategyCard.update] Failed: {e}", exc_info=True)


class StrategyPickerSidebar(QDialog, ThemedMixin):
    """
    Compact floating sidebar for switching active strategy.
    Non-modal — can stay open while trading. Uses database-backed strategy manager.

    MODERN MINIMALIST DESIGN - Matches other dialogs.
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

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.setFixedWidth(420)
            self.setMinimumHeight(650)
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
            self._create_error_dialog(parent)

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
        self.main_card = None

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent, Qt.Window | Qt.Tool)
            self.setWindowTitle("Strategy Picker - ERROR")
            self.setMinimumWidth(400)
            self.setMinimumHeight(300)

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)

            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel(f"❌ Failed to initialize strategy picker:")
            error_label.setWordWrap(True)
            error_label.setStyleSheet(f"color: {self._c.RED_BRIGHT}; padding: {self._sp.PAD_XL}px; font-size: {self._ty.SIZE_MD}pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BLUE};
                    color: white;
                    border: none;
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    min-width: 100px;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BLUE_DARK};
                }}
            """)
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn, 0, Qt.AlignCenter)

            root.addWidget(main_card)

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._create_error_dialog] Failed: {e}", exc_info=True)

    def _create_title_bar(self):
        """Create custom title bar with close button."""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(f"background: {self._c.BG_PANEL}; border-top-left-radius: {self._sp.RADIUS_LG}px; border-top-right-radius: {self._sp.RADIUS_LG}px;")

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(self._sp.PAD_MD, 0, self._sp.PAD_MD, 0)

        title = QLabel("⚡ Strategy Picker")
        title.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_LG}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
        """)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_DIM};
                border: none;
                border-radius: {self._sp.RADIUS_SM}px;
                font-size: {self._ty.SIZE_MD}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self._c.RED};
                color: white;
            }}
        """)
        close_btn.clicked.connect(self.hide)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        return title_bar

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the sidebar.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            # Update main card style
            if hasattr(self, 'main_card') and self.main_card:
                self.main_card._apply_style()

            # Update activate button
            if self._activate_btn:
                self._activate_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {c.BLUE};
                        color: white;
                        border: none;
                        border-radius: {sp.RADIUS_MD}px;
                        padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                        font-size: {ty.SIZE_BODY}pt;
                        font-weight: {ty.WEIGHT_BOLD};
                        min-height: 40px;
                    }}
                    QPushButton:hover {{
                        background: {c.BLUE_DARK};
                    }}
                    QPushButton:disabled {{
                        background: {c.BG_HOVER};
                        color: {c.TEXT_DISABLED};
                    }}
                """)

            # Update status label
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color: {c.GREEN}; font-size: {ty.SIZE_XS}pt;")

            # Update card
            if self._card and safe_hasattr(self._card, 'apply_theme'):
                self._card.apply_theme()

            # Update confidence bars
            for bar in self._confidence_bars.values():
                if safe_hasattr(bar, 'apply_theme'):
                    bar.apply_theme()

            # Refresh list items to update colors
            self._refresh_list_colors()

            # Update list widget style
            if self._list:
                self._list.setStyleSheet(f"""
                    QListWidget {{
                        background: {c.BG_PANEL};
                        color: {c.TEXT_MAIN};
                        border: 1px solid {c.BORDER};
                        border-radius: {sp.RADIUS_MD}px;
                        font-size: {ty.SIZE_BODY}pt;
                        outline: none;
                    }}
                    QListWidget::item {{
                        padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                        border-bottom: 1px solid {c.BORDER};
                    }}
                    QListWidget::item:selected {{
                        background: {c.BG_SELECTED};
                        color: {c.BLUE};
                    }}
                    QListWidget::item:hover {{
                        background: {c.BG_HOVER};
                    }}
                """)

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
            # Root layout with margins for shadow effect
            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)
            root.setSpacing(0)

            # Main container card
            self.main_card = ModernCard(self, elevated=True)
            main_layout = QVBoxLayout(self.main_card)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # Custom title bar
            title_bar = self._create_title_bar()
            main_layout.addWidget(title_bar)

            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet(f"background: {self._c.BORDER}; max-height: 1px;")
            main_layout.addWidget(separator)

            # Content area
            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                             self._sp.PAD_XL, self._sp.PAD_XL)
            content_layout.setSpacing(self._sp.GAP_LG)

            # Active strategy card
            self._card = _StrategyCard()
            content_layout.addWidget(self._card)

            # FEATURE 3: Confidence scores group
            self._confidence_group = QGroupBox("📊 Signal Confidence")
            self._confidence_group.setStyleSheet(f"""
                QGroupBox {{
                    background: {self._c.BG_PANEL};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    margin-top: {self._sp.PAD_MD}px;
                    color: {self._c.TEXT_MAIN};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: {self._sp.PAD_MD}px;
                    padding: 0 {self._sp.PAD_XS}px;
                    color: {self._c.BLUE};
                    font-weight: {self._ty.WEIGHT_BOLD};
                }}
            """)
            confidence_layout = QVBoxLayout(self._confidence_group)
            confidence_layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD,
                                                self._sp.PAD_MD, self._sp.PAD_MD)
            confidence_layout.setSpacing(self._sp.GAP_SM)

            # Create confidence bars for each signal group
            signal_groups = ['BUY_CALL', 'BUY_PUT', 'EXIT_CALL', 'EXIT_PUT', 'HOLD']
            for signal in signal_groups:
                bar = _ConfidenceBar(signal)
                confidence_layout.addWidget(bar)
                self._confidence_bars[signal] = bar

            content_layout.addWidget(self._confidence_group)

            # Strategy list header
            list_header = QHBoxLayout()
            list_header.addWidget(QLabel("📋 All Strategies"))
            list_header.addStretch()
            content_layout.addLayout(list_header)

            # Strategy list
            self._list = QListWidget()
            self._list.setSelectionMode(QAbstractItemView.SingleSelection)
            self._list.itemDoubleClicked.connect(self._on_double_click)
            self._list.setStyleSheet(f"""
                QListWidget {{
                    background: {self._c.BG_PANEL};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    outline: none;
                }}
                QListWidget::item {{
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_MD}px;
                    border-bottom: 1px solid {self._c.BORDER};
                }}
                QListWidget::item:selected {{
                    background: {self._c.BG_SELECTED};
                    color: {self._c.BLUE};
                }}
                QListWidget::item:hover {{
                    background: {self._c.BG_HOVER};
                }}
            """)
            content_layout.addWidget(self._list, 1)

            # Activate button
            self._activate_btn = QPushButton("⚡ Activate Selected")
            self._activate_btn.clicked.connect(self._on_activate)
            content_layout.addWidget(self._activate_btn)

            # Footer
            foot = QHBoxLayout()
            foot.setSpacing(self._sp.GAP_MD)

            open_editor_btn = QPushButton("📋 Open Editor")
            open_editor_btn.setCursor(Qt.PointingHandCursor)
            open_editor_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    border: 1px solid {self._c.BORDER};
                    border-radius: {self._sp.RADIUS_MD}px;
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                    font-size: {self._ty.SIZE_BODY}pt;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background: {self._c.BORDER};
                }}
            """)
            open_editor_btn.clicked.connect(self._on_open_editor)
            foot.addWidget(open_editor_btn)

            foot.addStretch()

            # Status label
            self._status_lbl = QLabel()
            self._status_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._status_lbl.setStyleSheet(f"color: {self._c.GREEN}; font-size: {self._ty.SIZE_XS}pt;")
            foot.addWidget(self._status_lbl)

            content_layout.addLayout(foot)

            main_layout.addWidget(content)
            root.addWidget(self.main_card)

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
                    for sig in SIGNAL_GROUPS:
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
        """Activate a strategy by slug - with deadlock prevention"""
        try:
            c = self._c
            if not slug:
                logger.warning("Cannot activate: empty slug")
                return

            # First, check if this is already the active strategy
            current_active = strategy_manager.get_active_slug()
            if current_active == slug:
                logger.debug(f"Strategy {slug} is already active")
                # Still show success message
                strategy_data = strategy_manager.get(slug) or {}
                name = strategy_data.get("name", slug)

                if self._status_lbl:
                    self._status_lbl.setStyleSheet(f"color:{c.GREEN}; font-size:{self._ty.SIZE_XS}pt;")
                    self._status_lbl.setText(f"✓ Already active: {name}")
                    QTimer.singleShot(3000, lambda: self._status_lbl.clear() if self._status_lbl else None)
                return

            # Use a timer to perform the activation to prevent UI freezing
            def do_activation():
                try:
                    # Perform the activation
                    ok = strategy_manager.activate(slug)

                    if ok:
                        # Update UI on the main thread
                        QMetaObject.invokeMethod(
                            self,
                            "_on_activation_success",
                            Qt.QueuedConnection,
                            Q_ARG(str, slug)
                        )
                    else:
                        QMetaObject.invokeMethod(
                            self,
                            "_on_activation_failure",
                            Qt.QueuedConnection,
                            Q_ARG(str, slug)
                        )
                except Exception as e:
                    logger.error(f"[StrategyPickerSidebar.do_activation] Failed: {e}", exc_info=True)
                    QMetaObject.invokeMethod(
                        self,
                        "_on_activation_error",
                        Qt.QueuedConnection,
                        Q_ARG(str, str(e))
                    )

            # Run activation in a thread pool to avoid blocking
            from concurrent.futures import ThreadPoolExecutor
            executor = ThreadPoolExecutor(max_workers=1)
            executor.submit(do_activation)
            executor.shutdown(wait=False)

            # Show loading state
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.YELLOW}; font-size:{self._ty.SIZE_XS}pt;")
                self._status_lbl.setText(f"⏳ Activating strategy...")

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._activate] Failed for {slug}: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_activation_success(self, slug: str):
        """Handle successful activation on UI thread"""
        try:
            c = self._c
            self.refresh()

            # Emit signal with a delay to prevent recursion
            QTimer.singleShot(100, lambda: self.strategy_activated.emit(slug))

            strategy_data = strategy_manager.get(slug) or {}
            name = strategy_data.get("name", slug)

            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.GREEN}; font-size:{self._ty.SIZE_XS}pt;")
                self._status_lbl.setText(f"✓ Activated: {name}")
                QTimer.singleShot(3000, lambda: self._status_lbl.clear() if self._status_lbl else None)

        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._on_activation_success] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_activation_failure(self, slug: str):
        """Handle activation failure on UI thread"""
        try:
            c = self._c
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.RED}; font-size:{self._ty.SIZE_XS}pt;")
                self._status_lbl.setText(f"✗ Failed to activate {slug}")
                QTimer.singleShot(3000, lambda: self._status_lbl.clear() if self._status_lbl else None)
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._on_activation_failure] Failed: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_activation_error(self, error: str):
        """Handle activation error on UI thread"""
        try:
            c = self._c
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color:{c.RED}; font-size:{self._ty.SIZE_XS}pt;")
                self._status_lbl.setText(f"✗ Error: {error[:50]}...")
                QTimer.singleShot(5000, lambda: self._status_lbl.clear() if self._status_lbl else None)
        except Exception as e:
            logger.error(f"[StrategyPickerSidebar._on_activation_error] Failed: {e}", exc_info=True)

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
            self.main_card = None

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