"""
dynamic_signal_debug_popup_db.py
=================================
A live-updating popup that shows every detail of the DynamicSignalEngine
evaluation: indicator values, rule-by-rule results, group fired/not-fired
status, conflict detection, confidence scores, and the final resolved signal.
MODERN MINIMALIST DESIGN - Matches DailyTradeSettingGUI, BrokerageSettingGUI, etc.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

from __future__ import annotations
import logging
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QBrush
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QGroupBox,
    QGridLayout, QTabWidget, QTextEdit, QProgressBar,
)

from Utils.safe_getattr import safe_hasattr, safe_getattr
# Import state manager
from data.trade_state_manager import state_manager

from strategy.dynamic_signal_engine import SIGNAL_COLORS, SIGNAL_LABELS, SIGNAL_GROUPS

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


def _get_signal_colors():
    """Get signal colors from theme manager, falling back to imported ones if needed"""
    try:
        c = theme_manager.palette
        return {
            "BUY_CALL": c.GREEN,
            "BUY_PUT": c.BLUE,
            "EXIT_CALL": c.RED,
            "EXIT_PUT": c.ORANGE,
            "HOLD": c.YELLOW,
            "WAIT": c.TEXT_DISABLED
        }
    except Exception:
        # Fallback to imported colors if theme_manager not available
        return SIGNAL_COLORS


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


class ModernHeader(QLabel):
    """Modern header with underline accent."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("modernHeader")
        self._apply_style()

    def _apply_style(self):
        c = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing

        self.setStyleSheet(f"""
            QLabel#modernHeader {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_XL}pt;
                font-weight: {ty.WEIGHT_BOLD};
                padding-bottom: {sp.PAD_SM}px;
                border-bottom: 2px solid {c.BLUE};
                margin-bottom: {sp.PAD_MD}px;
            }}
        """)


class StatusBadge(QLabel):
    """Status badge with color-coded background."""

    def __init__(self, text="", status="neutral"):
        super().__init__(text)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(80)
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


class ScrollableTabWidget(QWidget):
    """Tab widget with scrollable content area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container widget for scrollable content
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(theme_manager.spacing.GAP_LG)

        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)

    def add_widget(self, widget):
        """Add a widget to the scrollable area."""
        self.container_layout.addWidget(widget)

    def add_stretch(self):
        """Add stretch to the scrollable area."""
        self.container_layout.addStretch()


def _header_label(text: str, color_token: str = "TEXT_DIM", size_token: str = "SIZE_XS") -> QLabel:
    try:
        c = theme_manager.palette
        ty = theme_manager.typography
        color = c.get(color_token, c.TEXT_DIM)
        size = ty.get(size_token, ty.SIZE_XS)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: {size}pt; font-weight: {ty.WEIGHT_BOLD};")
        return lbl
    except Exception as e:
        logger.error(f"[_header_label] Failed: {e}", exc_info=True)
        lbl = QLabel(text)
        return lbl


def _value_label(text: str, color_token: str = "TEXT_MAIN", size_token: str = "SIZE_SM") -> QLabel:
    try:
        c = theme_manager.palette
        ty = theme_manager.typography
        color = c.get(color_token, c.TEXT_MAIN)
        size = ty.get(size_token, ty.SIZE_SM)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            color: {color}; 
            font-size: {size}pt; 
            font-weight: {ty.WEIGHT_BOLD};
            background: {c.BG_HOVER};
            padding: {theme_manager.spacing.PAD_XS}px {theme_manager.spacing.PAD_SM}px;
            border-radius: {theme_manager.spacing.RADIUS_SM}px;
        """)
        return lbl
    except Exception as e:
        logger.error(f"[_value_label] Failed: {e}", exc_info=True)
        lbl = QLabel(text)
        return lbl


class _SignalBadge(QLabel, ThemedMixin):
    """Pill-shaped label showing a signal value."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setAlignment(Qt.AlignCenter)
            self.setMinimumWidth(150)
            self.setFixedHeight(48)
            self._set("WAIT")
            self.apply_theme()
        except Exception as e:
            logger.error(f"[_SignalBadge.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setAlignment(Qt.AlignCenter)
            self.setText("ERROR")

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._last_signal = "WAIT"
        self._signal_colors = _get_signal_colors()

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the badge"""
        try:
            self._signal_colors = _get_signal_colors()
            self._set(self._last_signal)
        except Exception as e:
            logger.error(f"[_SignalBadge.apply_theme] Failed: {e}", exc_info=True)

    def _set(self, signal_value: str):
        try:
            c = self._c
            color = self._signal_colors.get(signal_value, self._signal_colors["WAIT"])
            label = SIGNAL_LABELS.get(signal_value, signal_value)
            self.setText(label)
            self.setStyleSheet(f"""
                QLabel {{
                    background: {color}22;
                    color: {color};
                    border: 2px solid {color};
                    border-radius: {self._sp.RADIUS_LG}px;
                    font-size: {self._ty.SIZE_XL}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                }}
            """)
            self._last_signal = signal_value
        except Exception as e:
            logger.error(f"[_SignalBadge._set] Failed: {e}", exc_info=True)

    def update_signal(self, signal_value: str):
        try:
            if signal_value != self._last_signal:
                self._set(signal_value)
        except Exception as e:
            logger.error(f"[_SignalBadge.update_signal] Failed: {e}", exc_info=True)


class _RuleRow:
    """One row in a rule table: rule expression | current values | result | weight."""

    def __init__(self, table: QTableWidget, row: int):
        try:
            self.table = table
            self.row = row
        except Exception as e:
            logger.error(f"[_RuleRow.__init__] Failed: {e}", exc_info=True)

    def set(self, rule_str: str, lhs_val: str, op: str, rhs_val: str, result: bool,
            weight: float = 1.0, error: str = "", is_blocker: bool = False):
        """
        FEATURE 3: Added weight parameter to display rule weights.
        """
        try:
            c = theme_manager.palette
            ty = theme_manager.typography
            sp = theme_manager.spacing

            # Annotate the rule expression with a BLOCKER tag when it is the
            # first False rule in an AND chain that prevents the group firing.
            display_rule = f"⚠ {rule_str}  [► BLOCKER]" if is_blocker else rule_str

            # Add weight indicator
            if weight != 1.0:
                display_rule += f"  (w={weight:.1f})"

            items = [
                (display_rule, c.YELLOW if is_blocker else c.TEXT_MAIN),
                (lhs_val, c.BLUE),
                (op, c.YELLOW),
                (rhs_val, c.ORANGE),
                (f"✅  TRUE (w={weight:.1f})" if result else f"❌  FALSE (w={weight:.1f})", c.GREEN if result else c.RED),
            ]
            if error:
                items[-1] = (f"⚠ {error[:40]}", c.YELLOW)

            for col, (text, color) in enumerate(items):
                item = QTableWidgetItem(str(text) if text is not None else "")
                item.setForeground(QColor(color))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if is_blocker:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QColor(c.RED + "18"))
                self.table.setItem(self.row, col, item)

        except Exception as e:
            logger.error(f"[_RuleRow.set] Failed: {e}", exc_info=True)


class _ConfidenceBar(QWidget, ThemedMixin):
    """
    FEATURE 3: Progress bar showing confidence percentage.
    """
    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(self._sp.GAP_SM)

            self._bar = QProgressBar()
            self._bar.setRange(0, 100)
            self._bar.setTextVisible(False)
            self._bar.setFixedHeight(16)
            self._bar.setMinimumWidth(150)

            self._label = QLabel("0%")
            self._label.setFixedWidth(50)

            layout.addWidget(self._bar)
            layout.addWidget(self._label)

            self.apply_theme()
        except Exception as e:
            logger.error(f"[_ConfidenceBar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._bar = None
        self._label = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors"""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            if self._bar:
                self._bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                        background: {c.BG_HOVER};
                        text-align: center;
                    }}
                    QProgressBar::chunk {{
                        background: {c.BLUE};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                """)

            if self._label:
                self._label.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XS}pt;")
        except Exception as e:
            logger.error(f"[_ConfidenceBar.apply_theme] Failed: {e}", exc_info=True)

    def set_confidence(self, confidence: float, threshold: float = 0.6):
        """
        Set confidence value (0.0 to 1.0) and threshold.
        """
        try:
            c = self._c
            percent = int(confidence * 100)
            threshold_pct = int(threshold * 100)

            # Color based on confidence relative to threshold
            if confidence >= threshold:
                color = c.GREEN
            elif confidence >= threshold * 0.7:
                color = c.YELLOW
            else:
                color = c.RED

            if self._bar:
                self._bar.setValue(percent)
                self._bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {c.BORDER};
                        border-radius: {self._sp.RADIUS_SM}px;
                        background: {c.BG_HOVER};
                        text-align: center;
                    }}
                    QProgressBar::chunk {{
                        background: {color};
                        border-radius: {self._sp.RADIUS_SM}px;
                    }}
                """)

            if self._label:
                self._label.setText(f"{percent}%")
                self._label.setStyleSheet(f"color: {color}; font-size: {self._ty.SIZE_XS}pt; font-weight: {self._ty.WEIGHT_BOLD};")

        except Exception as e:
            logger.error(f"[_ConfidenceBar.set_confidence] Failed: {e}", exc_info=True)


class _GroupPanel(ModernCard, ThemedMixin):
    """
    Panel for one signal group (BUY_CALL, BUY_PUT, etc.).
    Shows logic mode, fired status, confidence score, and a per-rule table.
    FEATURE 3: Added confidence display.
    """

    def __init__(self, signal: str, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            label = SIGNAL_LABELS.get(signal, signal)
            super().__init__(parent)
            self.signal = signal

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._signal_colors = _get_signal_colors()
            self._color = self._signal_colors.get(signal, self._c.TEXT_DISABLED)
            self._setup_ui(label)
            self.apply_theme()
        except Exception as e:
            logger.error(f"[_GroupPanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.signal = signal
            self._color = self._c.TEXT_DISABLED

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.signal = ""
        self._color = None
        self._logic_lbl = None
        self._fired_badge = None
        self._enabled_badge = None
        self._confidence_bar = None
        self._table = None
        self._no_rules_lbl = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the group panel"""
        try:
            c = self._c
            sp = self._sp

            self._signal_colors = _get_signal_colors()
            self._color = self._signal_colors.get(self.signal, c.TEXT_DISABLED)

            # Update table style
            if self._table:
                self._table.setStyleSheet(f"""
                    QTableWidget {{ 
                        alternate-background-color: {c.BG_ROW_B}; 
                        background: {c.BG_ROW_A};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                    QHeaderView::section {{
                        background-color: {c.BG_HOVER};
                        color: {c.TEXT_MAIN};
                        font-weight: {self._ty.WEIGHT_BOLD};
                        padding: {sp.PAD_XS}px;
                        border: none;
                        border-right: 1px solid {c.BORDER};
                    }}
                    QTableCornerButton::section {{
                        background-color: {c.BG_HOVER};
                        border: none;
                    }}
                """)

            # Update no rules label
            if self._no_rules_lbl:
                self._no_rules_lbl.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-size: {self._ty.SIZE_XS}pt; padding: {sp.PAD_SM}px;")

        except Exception as e:
            logger.error(f"[_GroupPanel.apply_theme] Failed: {e}", exc_info=True)

    def _setup_ui(self, label):
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            root = QVBoxLayout(self)
            root.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
            root.setSpacing(sp.GAP_MD)

            # Header row
            header = QHBoxLayout()
            header.setSpacing(sp.GAP_MD)

            # Title with color
            title_lbl = QLabel(label)
            title_lbl.setStyleSheet(f"""
                color: {self._color};
                font-size: {ty.SIZE_MD}pt;
                font-weight: {ty.WEIGHT_BOLD};
            """)
            header.addWidget(title_lbl)

            header.addStretch()

            # Logic
            self._logic_lbl = _header_label("AND", "TEXT_DIM")
            header.addWidget(self._logic_lbl)

            # Confidence bar
            self._confidence_bar = _ConfidenceBar()
            header.addWidget(self._confidence_bar)

            # Fired badge
            self._fired_badge = StatusBadge("NOT FIRED", "neutral")
            header.addWidget(self._fired_badge)

            # Enabled badge
            self._enabled_badge = StatusBadge("enabled", "success")

            root.addLayout(header)

            # Rule table
            self._table = QTableWidget(0, 5)
            self._table.setHorizontalHeaderLabels(["Rule Expression", "LHS Value", "Op", "RHS Value", "Result"])

            # Style the table headers
            header = self._table.horizontalHeader()
            header.setStyleSheet(f"""
                QHeaderView::section {{
                    background-color: {c.BG_HOVER};
                    color: {c.TEXT_MAIN};
                    font-weight: {ty.WEIGHT_BOLD};
                    padding: {sp.PAD_SM}px;
                    border: none;
                    border-right: 1px solid {c.BORDER};
                }}
            """)

            # Set column resize modes
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for i in range(1, 5):
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

            self._table.verticalHeader().setVisible(False)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._table.setSelectionBehavior(QTableWidget.SelectRows)
            self._table.setAlternatingRowColors(True)
            self._table.setMinimumHeight(80)
            self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            root.addWidget(self._table)

            self._no_rules_lbl = QLabel("  ⚪ No rules configured for this signal.")
            self._no_rules_lbl.hide()
            root.addWidget(self._no_rules_lbl)

        except Exception as e:
            logger.error(f"[_GroupPanel._setup_ui] Failed: {e}", exc_info=True)

    def update(self, rule_results: List[Dict], fired: bool, logic: str, enabled: bool,
               confidence: float = 0.0, threshold: float = 0.6, indicator_cache: Dict = None):
        """
        FEATURE 3: Added confidence and threshold parameters.
        """
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Logic label
            if self._logic_lbl is not None:
                self._logic_lbl.setText(f"Logic: {logic}")

            # Enabled badge
            if self._enabled_badge is not None:
                if enabled:
                    self._enabled_badge.setText("enabled")
                    self._enabled_badge.set_status("success")
                else:
                    self._enabled_badge.setText("disabled")
                    self._enabled_badge.set_status("error")

            # Fired badge
            if self._fired_badge is not None:
                if fired:
                    self._fired_badge.setText("FIRED")
                    self._fired_badge.set_status("success")
                else:
                    self._fired_badge.setText("NOT FIRED")
                    self._fired_badge.set_status("neutral")

            # FEATURE 3: Update confidence bar
            if self._confidence_bar is not None:
                self._confidence_bar.set_confidence(confidence, threshold)

            if not rule_results or self._table is None:
                if self._table is not None:
                    self._table.hide()
                if self._no_rules_lbl is not None:
                    self._no_rules_lbl.show()
                if self._table is not None:
                    self._table.setRowCount(0)
                return

            if self._no_rules_lbl is not None:
                self._no_rules_lbl.hide()
            if self._table is not None:
                self._table.show()
                self._table.setRowCount(len(rule_results))

            # Identify the first-blocker index: first False in an AND chain
            # (only meaningful when logic == AND and group did not fire)
            first_blocker_idx = -1
            if logic.upper() == "AND" and not fired:
                for idx, entry in enumerate(rule_results):
                    if not entry.get("result", True):
                        first_blocker_idx = idx
                        break

            for i, entry in enumerate(rule_results):
                try:
                    rule_str = entry.get("rule", "?")
                    result = entry.get("result", False)
                    error = entry.get("error", "")
                    is_blocker = (i == first_blocker_idx)

                    # FEATURE 3: Get rule weight
                    weight = entry.get("weight", 1.0)

                    # --- Use pre-computed values from dynamic_signal_engine (new fields) ---
                    lhs_raw = entry.get("lhs_value")  # float or None
                    rhs_raw = entry.get("rhs_value")  # float or None
                    detail = entry.get("detail", "")  # "47.2300 > 50.0000 → ✗"

                    # Format values for display; fall back to old cache-parsing if absent
                    if lhs_raw is not None:
                        lhs_val = f"{lhs_raw:.4f}"
                    else:
                        lhs_val, _, _ = _parse_rule_display(rule_str, indicator_cache)

                    if rhs_raw is not None:
                        rhs_val = f"{rhs_raw:.4f}"
                    else:
                        _, _, rhs_val = _parse_rule_display(rule_str, indicator_cache)

                    # Extract operator from rule string
                    op = "?"
                    for _op in [">=", "<=", "!=", "==", ">", "<"]:
                        if f" {_op} " in rule_str:
                            op = _op
                            break

                    _RuleRow(self._table, i).set(rule_str, lhs_val, op, rhs_val, result, weight, error, is_blocker)

                except Exception as e:
                    logger.warning(f"Failed to update rule row {i}: {e}", exc_info=True)
                    continue

            if self._table is not None:
                self._table.setFixedHeight(30 * len(rule_results) + 30)

        except Exception as e:
            logger.error(f"[_GroupPanel.update] Failed: {e}", exc_info=True)


def _parse_rule_display(rule_str: str, cache: Dict = None) -> Tuple[str, str, str]:
    """
    Split rule string like 'RSI(14) > 55' into lhs/op/rhs.
    If indicator_cache has the computed value, show it.
    """
    try:
        if not rule_str:
            return "?", "?", "?"

        OPERATORS = [">=", "<=", "!=", "==", ">", "<"]

        for op in OPERATORS:
            if f" {op} " in rule_str:
                parts = rule_str.split(f" {op} ", 1)
                lhs_name = parts[0].strip()
                rhs_name = parts[1].strip() if len(parts) > 1 else "?"

                # Look up current value from indicator cache
                lhs_val = _lookup_cache(lhs_name, cache)
                rhs_val = _lookup_cache(rhs_name, cache)

                # If we couldn't find values, try to extract the raw numbers from the rule string
                if lhs_val == lhs_name and cache is not None:
                    # Try to extract from cache by indicator name without params
                    lhs_base = lhs_name.split('(')[0].lower()
                    for key, series in cache.items():
                        if key.startswith(lhs_base + '_'):
                            try:
                                import pandas as pd
                                if isinstance(series, pd.Series) and len(series) > 0:
                                    val = series.iloc[-1]
                                    if val is not None:
                                        import math
                                        if not math.isnan(float(val)):
                                            lhs_val = f"{lhs_name} [{float(val):.4f}]"
                                            break
                            except Exception:
                                pass

                if rhs_val == rhs_name and cache is not None and rhs_name not in ["?", "scalar"]:
                    rhs_base = rhs_name.split('(')[0].lower()
                    for key, series in cache.items():
                        if key.startswith(rhs_base + '_'):
                            try:
                                import pandas as pd
                                if isinstance(series, pd.Series) and len(series) > 0:
                                    val = series.iloc[-1]
                                    if val is not None:
                                        import math
                                        if not math.isnan(float(val)):
                                            rhs_val = f"{rhs_name} [{float(val):.4f}]"
                                            break
                            except Exception:
                                pass

                return lhs_val, op, rhs_val

        return "?", "?", "?"

    except Exception as e:
        logger.error(f"[_parse_rule_display] Failed: {e}", exc_info=True)
        return "?", "?", "?"


def _lookup_cache(name: str, cache: Dict = None) -> str:
    """Try to find a computed indicator value from the engine cache."""
    try:
        if cache is None or not cache:
            return name

        # Extract the base indicator name (remove parameters)
        name_lower = name.lower().split('(')[0].strip()

        # First try exact match
        for key, series in cache.items():
            if key.startswith(name_lower + '_'):
                try:
                    import pandas as pd
                    if isinstance(series, pd.Series) and len(series) > 0:
                        val = series.iloc[-1]
                        if val is not None and not pd.isna(val):
                            import math
                            if not math.isnan(float(val)):
                                # Format nicely
                                if abs(val) < 0.01 or abs(val) > 1000:
                                    return f"{name}  [{val:.6f}]"
                                else:
                                    return f"{name}  [{val:.2f}]"
                except Exception:
                    pass

        # If it's a scalar value, return it as is
        try:
            float_val = float(name)
            return f"{float_val:.2f}"
        except ValueError:
            pass

        return name

    except Exception as e:
        logger.error(f"[_lookup_cache] Failed: {e}", exc_info=True)
        return name


class _IndicatorCachePanel(ModernCard, ThemedMixin):
    """Tab showing raw computed indicator values from the engine cache."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD)
            layout.setSpacing(self._sp.GAP_MD)

            header = _header_label("Indicator Values", "BLUE", "SIZE_MD")
            layout.addWidget(header)

            self._table = QTableWidget(0, 3)
            self._table.setHorizontalHeaderLabels(["Indicator", "Latest Value", "Previous Value"])

            # Style the table headers
            header_view = self._table.horizontalHeader()
            header_view.setStyleSheet(f"""
                QHeaderView::section {{
                    background-color: {self._c.BG_HOVER};
                    color: {self._c.TEXT_MAIN};
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_SM}px;
                    border: none;
                    border-right: 1px solid {self._c.BORDER};
                }}
            """)

            header_view.setSectionResizeMode(0, QHeaderView.Stretch)
            header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)

            self._table.verticalHeader().setVisible(False)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._table.setAlternatingRowColors(True)
            layout.addWidget(self._table)

            self.apply_theme()

        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._table = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the panel"""
        try:
            c = self._c
            sp = self._sp
            if self._table:
                self._table.setStyleSheet(f"""
                    QTableWidget {{ 
                        alternate-background-color: {c.BG_ROW_B}; 
                        background: {c.BG_ROW_A};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                """)
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.apply_theme] Failed: {e}", exc_info=True)

    def update_cache(self, cache: Dict):
        """Legacy path: cache is {key: pd.Series}."""
        try:
            import pandas as pd
            rows = []
            for key, series in cache.items():
                try:
                    if isinstance(series, pd.Series) and len(series) > 0:
                        latest = series.iloc[-1]
                        prev = series.iloc[-2] if len(series) >= 2 else None
                        latest_str = f"{float(latest):.6f}" if latest is not None else "N/A"
                        prev_str = f"{float(prev):.6f}" if prev is not None else "N/A"
                    else:
                        latest_str = prev_str = "N/A"
                except Exception:
                    latest_str = prev_str = "err"
                rows.append((key, latest_str, prev_str))
            self._render_rows(rows)
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.update_cache] Failed: {e}", exc_info=True)

    def update_from_values(self, indicator_values: Dict):
        """
        New path: indicator_values is {cache_key: {"last": float, "prev": float}}
        as emitted directly by DynamicSignalEngine.evaluate().
        No pandas needed — values are already plain floats.
        """
        try:
            c = self._c
            rows = []
            for key, val in indicator_values.items():
                try:
                    last = val.get("last") if isinstance(val, dict) else None
                    prev = val.get("prev") if isinstance(val, dict) else None
                    last_str = f"{last:.6f}" if last is not None else "N/A"
                    prev_str = f"{prev:.6f}" if prev is not None else "N/A"
                except Exception:
                    last_str = prev_str = "err"
                rows.append((key, last_str, prev_str))
            self._render_rows(rows)
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.update_from_values] Failed: {e}", exc_info=True)

    def _render_rows(self, rows):
        """Shared table-population helper."""
        try:
            c = self._c
            if self._table is None:
                logger.warning("_render_rows called with None table")
                return

            self._table.setRowCount(len(rows))
            for i, (key, latest, prev) in enumerate(rows):
                try:
                    for j, (text, color) in enumerate([(key, c.TEXT_DIM), (latest, c.BLUE), (prev, c.TEXT_DIM)]):
                        item = QTableWidgetItem(str(text) if text is not None else "N/A")
                        item.setForeground(QColor(color))
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        self._table.setItem(i, j, item)
                except Exception as e:
                    logger.warning(f"Failed to render row {i}: {e}")
                    continue
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel._render_rows] Failed: {e}", exc_info=True)


class _ConfidencePanel(ModernCard, ThemedMixin):
    """
    FEATURE 3: Tab showing confidence scores for all signal groups.
    """
    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD)
            layout.setSpacing(self._sp.GAP_LG)

            # Header
            header = _header_label("Confidence Scores", "BLUE", "SIZE_MD")
            layout.addWidget(header)

            # Explanation card
            self._explanation_card = ModernCard()
            expl_layout = QVBoxLayout(self._explanation_card)
            self._explanation_lbl = QLabel("No signal evaluation yet")
            self._explanation_lbl.setWordWrap(True)
            expl_layout.addWidget(self._explanation_lbl)
            layout.addWidget(self._explanation_card)

            # Confidence bars for each group
            self._confidence_bars = {}
            for sig in SIGNAL_GROUPS:
                group_box = ModernCard()
                group_layout = QVBoxLayout(group_box)
                group_layout.setSpacing(self._sp.GAP_MD)

                # Header with signal name and color
                sig_header = QHBoxLayout()
                sig_color = _get_signal_colors().get(sig, self._c.TEXT_DIM)
                sig_lbl = QLabel(SIGNAL_LABELS.get(sig, sig))
                sig_lbl.setStyleSheet(f"color: {sig_color}; font-size: {self._ty.SIZE_MD}pt; font-weight: {self._ty.WEIGHT_BOLD};")
                sig_header.addWidget(sig_lbl)
                sig_header.addStretch()

                # Confidence bar
                bar = _ConfidenceBar()
                self._confidence_bars[sig] = bar
                sig_header.addWidget(bar)

                group_layout.addLayout(sig_header)

                # Threshold line
                threshold_layout = QHBoxLayout()
                threshold_layout.addWidget(QLabel("Threshold:"))
                self._threshold_lbl = QLabel("60%")
                self._threshold_lbl.setStyleSheet(f"color: {self._c.YELLOW}; font-weight: {self._ty.WEIGHT_BOLD};")
                threshold_layout.addWidget(self._threshold_lbl)
                threshold_layout.addStretch()
                group_layout.addLayout(threshold_layout)

                layout.addWidget(group_box)

            layout.addStretch()
            self.apply_theme()

        except Exception as e:
            logger.error(f"[_ConfidencePanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._explanation_card = None
        self._explanation_lbl = None
        self._threshold_lbl = None
        self._confidence_bars = {}

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the panel"""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            if self._explanation_card:
                self._explanation_card._apply_style()

            if self._explanation_lbl:
                self._explanation_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt;")

            if self._threshold_lbl:
                self._threshold_lbl.setStyleSheet(f"color: {c.YELLOW}; font-weight: {ty.WEIGHT_BOLD};")

        except Exception as e:
            logger.error(f"[_ConfidencePanel.apply_theme] Failed: {e}", exc_info=True)

    def update_confidence(self, confidence_dict: Dict[str, float], threshold: float = 0.6, explanation: str = ""):
        """
        Update confidence scores for all groups.
        """
        try:
            c = self._c

            # Update explanation
            if explanation:
                self._explanation_lbl.setText(explanation)
            else:
                self._explanation_lbl.setText("No explanation available")

            # Update threshold display
            threshold_pct = int(threshold * 100)
            self._threshold_lbl.setText(f"{threshold_pct}%")

            # Update bars
            for sig, bar in self._confidence_bars.items():
                conf = confidence_dict.get(sig, 0.0)
                bar.set_confidence(conf, threshold)

        except Exception as e:
            logger.error(f"[_ConfidencePanel.update_confidence] Failed: {e}", exc_info=True)


class _RawJsonPanel(ModernCard, ThemedMixin):
    """Tab showing the raw evaluate() result dict as JSON."""

    def __init__(self, parent=None):
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD, self._sp.PAD_MD)

            header = _header_label("Raw JSON Data", "BLUE", "SIZE_MD")
            layout.addWidget(header)

            self._text_edit = QTextEdit()
            self._text_edit.setReadOnly(True)
            layout.addWidget(self._text_edit)

            self.apply_theme()
        except Exception as e:
            logger.error(f"[_RawJsonPanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the panel"""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            self._text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background: {c.BG_PANEL};
                    color: {c.TEXT_MAIN};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    font-family: '{ty.FONT_MONO}';
                    font-size: {ty.SIZE_XS}pt;
                }}
            """)
        except Exception as e:
            logger.error(f"[_RawJsonPanel.apply_theme] Failed: {e}", exc_info=True)

    def update_result(self, result: Dict):
        try:
            if result is None:
                self._text_edit.setPlainText("No data available")
                return

            def _default(obj):
                try:
                    return str(obj)
                except Exception:
                    return "<unserializable>"

            try:
                text = json.dumps(result, indent=2, default=_default)
            except Exception as e:
                text = f"Serialisation error: {e}"
            self._text_edit.setPlainText(text)
        except Exception as e:
            logger.error(f"[_RawJsonPanel.update_result] Failed: {e}", exc_info=True)
            self._text_edit.setPlainText(f"Error updating: {e}")


class DynamicSignalDebugPopup(QDialog, ThemedMixin):
    """
    Non-modal popup that lives alongside the main TradingGUI window.
    Call refresh() every second (or from _tick_fast) to keep it live.
    Works with database-backed signal engine.
    FEATURE 3: Added confidence display tab.
    UPDATED: Now uses state_manager for state access.
    MODERN MINIMALIST DESIGN - Matches other dialogs.
    """

    def __init__(self, trading_app, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, Qt.Window)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.trading_app = trading_app
            self.setWindowTitle("🔬 Signal Engine Debug")

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self.resize(1000, 800)
            self.setMinimumSize(800, 600)

            # Internal state
            self._last_signal_value: str = ""
            self._auto_refresh = True
            self._indicator_cache: Dict = {}
            self._current_strategy_slug: Optional[str] = None
            self._last_confidence: Dict[str, float] = {}
            self._last_threshold: float = 0.6

            self._build_ui()
            self.apply_theme()

            # Auto-refresh every second when visible
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._maybe_refresh)
            self._timer.start(1000)

            logger.info("DynamicSignalDebugPopup (database) initialized with state_manager")

        except Exception as e:
            logger.critical(f"[DynamicSignalDebugPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.trading_app = None
        self._last_signal_value = ""
        self._auto_refresh = True
        self._indicator_cache = {}
        self._current_strategy_slug = None
        self._last_confidence = {}
        self._last_threshold = 0.6
        self._timer = None
        self._signal_badge = None
        self._lbl_conflict = None
        self._lbl_available = None
        self._lbl_symbol = None
        self._lbl_last_close = None
        self._lbl_bars = None
        self._lbl_timestamp = None
        self._lbl_strategy = None
        self._fired_pills = {}
        self._group_panels = {}
        self._cache_panel = None
        self._json_panel = None
        self._confidence_panel = None
        self._tabs = None
        self._groups_layout = None
        self._status_lbl = None
        self._auto_chk = None
        self.main_card = None

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent, Qt.Window)
            self.setWindowTitle("Signal Debug - ERROR")
            self.setMinimumSize(400, 300)

            # Set window flags for modern look
            self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            root = QVBoxLayout(self)
            root.setContentsMargins(20, 20, 20, 20)

            main_card = ModernCard(self, elevated=True)
            layout = QVBoxLayout(main_card)
            layout.setContentsMargins(self._sp.PAD_XL, self._sp.PAD_XL,
                                     self._sp.PAD_XL, self._sp.PAD_XL)

            error_label = QLabel(f"❌ Failed to initialize debug popup:\n{e}")
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
            logger.error(f"[DynamicSignalDebugPopup._create_error_dialog] Failed: {e}", exc_info=True)

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            sp = self._sp

            # Update main card style
            if hasattr(self, 'main_card'):
                self.main_card._apply_style()

            # Update all child widgets that have apply_theme methods
            if self._signal_badge and safe_hasattr(self._signal_badge, 'apply_theme'):
                self._signal_badge.apply_theme()

            if self._cache_panel and safe_hasattr(self._cache_panel, 'apply_theme'):
                self._cache_panel.apply_theme()

            if self._confidence_panel and safe_hasattr(self._confidence_panel, 'apply_theme'):
                self._confidence_panel.apply_theme()

            if self._json_panel and safe_hasattr(self._json_panel, 'apply_theme'):
                self._json_panel.apply_theme()

            for panel in self._group_panels.values():
                if safe_hasattr(panel, 'apply_theme'):
                    panel.apply_theme()

            # Update status label style
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

            logger.debug("[DynamicSignalDebugPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup.apply_theme] Failed: {e}", exc_info=True)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
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

            # Header
            header = ModernHeader("Signal Engine Debug")
            content_layout.addWidget(header)

            # Status header card
            status_header = self._build_status_header()
            content_layout.addWidget(status_header)

            # Tabs
            self._tabs = self._create_modern_tabs()
            content_layout.addWidget(self._tabs, 1)

            # Footer
            footer = self._build_footer()
            content_layout.addWidget(footer)

            main_layout.addWidget(content)
            root.addWidget(self.main_card)

        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup._build_ui] Failed: {e}", exc_info=True)
            raise

    def _create_title_bar(self):
        """Create custom title bar with close button."""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(f"background: {self._c.BG_PANEL}; border-top-left-radius: {self._sp.RADIUS_LG}px; border-top-right-radius: {self._sp.RADIUS_LG}px;")

        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(self._sp.PAD_MD, 0, self._sp.PAD_MD, 0)

        title = QLabel("🔬 Signal Engine Debug")
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
        close_btn.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(close_btn)

        return title_bar

    def _create_modern_tabs(self):
        """Create modern-styled tab widget."""
        tabs = QTabWidget()

        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                background: {self._c.BG_PANEL};
                margin-top: {self._sp.PAD_SM}px;
            }}
            QTabBar::tab {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_DIM};
                padding: {self._sp.PAD_SM}px {self._sp.PAD_XL}px;
                min-width: 130px;
                border: {self._sp.SEPARATOR}px solid {self._c.BORDER};
                border-bottom: none;
                border-radius: {self._sp.RADIUS_SM}px {self._sp.RADIUS_SM}px 0 0;
                font-size: {self._ty.SIZE_BODY}pt;
                margin-right: {self._sp.PAD_XS}px;
            }}
            QTabBar::tab:selected {{
                background: {self._c.BG_PANEL};
                color: {self._c.TEXT_MAIN};
                border-bottom: {self._sp.PAD_XS}px solid {self._c.BLUE};
                font-weight: {self._ty.WEIGHT_BOLD};
            }}
            QTabBar::tab:hover:!selected {{
                background: {self._c.BORDER};
                color: {self._c.TEXT_MAIN};
            }}
        """)

        # Tab 1: Group panels (scrollable)
        groups_widget = self._build_groups_tab()
        tabs.addTab(groups_widget, "📋 Signal Groups")

        # Tab 2: Indicator cache
        self._cache_panel = _IndicatorCachePanel()
        tabs.addTab(self._cache_panel, "📊 Indicators")

        # FEATURE 3: Confidence tab
        self._confidence_panel = _ConfidencePanel()
        tabs.addTab(self._confidence_panel, "📈 Confidence")

        # Tab 3: Raw JSON
        self._json_panel = _RawJsonPanel()
        tabs.addTab(self._json_panel, "{} Raw JSON")

        return tabs

    def _build_status_header(self) -> ModernCard:
        """Build status header card."""
        card = ModernCard()
        layout = QHBoxLayout(card)
        layout.setSpacing(self._sp.GAP_XL)

        # Signal badge (large)
        sig_col = QVBoxLayout()
        sig_col.addWidget(_header_label("FINAL SIGNAL", "TEXT_DIM", "SIZE_XS"), 0, Qt.AlignCenter)
        self._signal_badge = _SignalBadge()
        sig_col.addWidget(self._signal_badge)
        layout.addLayout(sig_col)

        # Vertical separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {self._c.BORDER};")
        layout.addWidget(sep)

        # Grid of status labels
        grid = QGridLayout()
        grid.setHorizontalSpacing(self._sp.PAD_XL)
        grid.setVerticalSpacing(self._sp.GAP_SM)

        row = 0
        # Conflict
        grid.addWidget(_header_label("CONFLICT", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_conflict = _value_label("No", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_conflict, row, 1)
        row += 1

        # Rules Available
        grid.addWidget(_header_label("RULES AVAILABLE", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_available = _value_label("—", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_available, row, 1)
        row += 1

        # Symbol
        grid.addWidget(_header_label("SYMBOL", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_symbol = _value_label("—", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_symbol, row, 1)
        row += 1

        # Last Close
        grid.addWidget(_header_label("LAST CLOSE", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_last_close = _value_label("—", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_last_close, row, 1)
        row += 1

        # Bars
        grid.addWidget(_header_label("BARS", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_bars = _value_label("—", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_bars, row, 1)
        row += 1

        # Last Refresh
        grid.addWidget(_header_label("LAST REFRESH", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_timestamp = _value_label("—", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_timestamp, row, 1)
        row += 1

        # Strategy
        grid.addWidget(_header_label("STRATEGY", "TEXT_DIM", "SIZE_XS"), row, 0)
        self._lbl_strategy = _value_label("—", "TEXT_MAIN", "SIZE_XS")
        grid.addWidget(self._lbl_strategy, row, 1)

        layout.addLayout(grid, 1)

        # Fired group indicators
        fired_col = QVBoxLayout()
        fired_col.addWidget(_header_label("FIRED GROUPS", "TEXT_DIM", "SIZE_XS"), 0, Qt.AlignCenter)
        fired_inner = QHBoxLayout()
        fired_inner.setSpacing(self._sp.GAP_SM)

        self._fired_pills = {}
        signal_colors = _get_signal_colors()
        for sig in SIGNAL_GROUPS:
            lbl = QLabel(sig.replace("_", "\n"))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedSize(70, 50)
            color = signal_colors.get(sig, self._c.TEXT_DISABLED)
            lbl.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    border: 1px solid {color};
                    border-radius: {self._sp.RADIUS_SM}px;
                    font-size: {self._ty.SIZE_XS}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_XS}px;
                }}
            """)
            self._fired_pills[sig] = lbl
            fired_inner.addWidget(lbl)

        fired_col.addLayout(fired_inner)
        layout.addLayout(fired_col)

        return card

    def _build_groups_tab(self) -> ScrollableTabWidget:
        """Build groups tab with scrollable content."""
        scrollable = ScrollableTabWidget()

        self._group_panels = {}
        for sig in SIGNAL_GROUPS:
            panel = _GroupPanel(sig)
            self._group_panels[sig] = panel
            scrollable.add_widget(panel)

        scrollable.add_stretch()
        return scrollable

    def _build_footer(self) -> ModernCard:
        """Build footer with controls."""
        card = ModernCard()
        layout = QHBoxLayout(card)
        layout.setSpacing(self._sp.GAP_MD)

        self._auto_chk = QCheckBox("Auto-refresh (1s)")
        self._auto_chk.setChecked(True)
        self._auto_chk.toggled.connect(self._on_auto_toggle)
        self._auto_chk.setStyleSheet(f"""
            QCheckBox {{
                color: {self._c.TEXT_MAIN};
                font-size: {self._ty.SIZE_SM}pt;
                spacing: {self._sp.GAP_SM}px;
            }}
            QCheckBox::indicator {{
                width: {self._sp.ICON_MD}px;
                height: {self._sp.ICON_MD}px;
                border: 2px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_SM}px;
            }}
            QCheckBox::indicator:checked {{
                background: {self._c.BLUE};
                border-color: {self._c.BLUE};
            }}
        """)
        layout.addWidget(self._auto_chk)

        layout.addStretch()

        self._status_lbl = QLabel("Waiting for data…")
        self._status_lbl.setStyleSheet(f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        refresh_btn = QPushButton("⟳ Refresh Now")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.BG_HOVER};
                color: {self._c.TEXT_MAIN};
                border: 1px solid {self._c.BORDER};
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_LG}px;
                font-size: {self._ty.SIZE_SM}pt;
                min-width: 120px;
            }}
            QPushButton:hover {{
                background: {self._c.BORDER};
            }}
        """)
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        close_btn = QPushButton("✕ Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._c.RED};
                color: white;
                border: none;
                border-radius: {self._sp.RADIUS_MD}px;
                padding: {self._sp.PAD_SM}px {self._sp.PAD_LG}px;
                font-size: {self._ty.SIZE_SM}pt;
                font-weight: {self._ty.WEIGHT_BOLD};
                min-width: 100px;
            }}
            QPushButton:hover {{
                background: {self._c.RED_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return card

    # ── Refresh logic ────────────────────────────────────────────────────────

    @pyqtSlot()
    def _maybe_refresh(self):
        try:
            if self._auto_refresh and self.isVisible():
                self.refresh()
        except Exception as e:
            logger.error(f"[_maybe_refresh] Failed: {e}", exc_info=True)

    def _on_auto_toggle(self, checked: bool):
        try:
            self._auto_refresh = checked
        except Exception as e:
            logger.error(f"[_on_auto_toggle] Failed: {e}", exc_info=True)

    @pyqtSlot()
    def refresh(self):
        """Pull the latest signal data from state_manager and update UI."""
        try:
            c = self._c
            ty = self._ty

            if self.trading_app is None:
                if self._status_lbl is not None:
                    self._status_lbl.setText("⚠  trading_app is None")
                return

            # UPDATED: Use state_manager to get state
            state = state_manager.get_state()
            if state is None:
                if self._status_lbl is not None:
                    self._status_lbl.setText("⚠  state_manager returned None")
                return

            # Get trend data (derivative_trend holds the last detect() result)
            trend_data = safe_getattr(state, "derivative_trend", None) or {}
            option_signal = trend_data.get("option_signal")

            if option_signal is None:
                if self._status_lbl is not None:
                    self._status_lbl.setText("⚠  No option_signal in state.derivative_trend yet.")
                return

            if not option_signal.get("available", False):
                if not option_signal.get("fired"):
                    if self._status_lbl is not None:
                        self._status_lbl.setText("ℹ  Engine available but no rules configured.")
                else:
                    if self._status_lbl is not None:
                        self._status_lbl.setText("ℹ  DynamicSignalEngine not available.")
                return

            # ── Update header ────────────────────────────────────────────────
            signal_val = option_signal.get("signal_value", "WAIT")
            if self._signal_badge is not None:
                self._signal_badge.update_signal(signal_val)

            conflict = option_signal.get("conflict", False)
            if self._lbl_conflict is not None:
                self._lbl_conflict.setText("YES" if conflict else "No")
                self._lbl_conflict.setStyleSheet(f"""
                    color: {c.RED if conflict else c.GREEN};
                    font-size: {ty.SIZE_XS}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    background: {c.BG_HOVER};
                    padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                    border-radius: {self._sp.RADIUS_SM}px;
                """)

            if self._lbl_available is not None:
                self._lbl_available.setText("Yes")
                self._lbl_available.setStyleSheet(f"""
                    color: {c.GREEN};
                    font-size: {ty.SIZE_XS}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    background: {c.BG_HOVER};
                    padding: {self._sp.PAD_XS}px {self._sp.PAD_SM}px;
                    border-radius: {self._sp.RADIUS_SM}px;
                """)

            # Symbol & price from trend_data
            symbol = trend_data.get("name", "—")
            close_list = trend_data.get("close") or []
            last_close = close_list[-1] if close_list else "—"
            if self._lbl_symbol is not None:
                self._lbl_symbol.setText(str(symbol))
            if self._lbl_last_close is not None:
                self._lbl_last_close.setText(str(last_close))

            # Bars
            if self._lbl_bars is not None:
                self._lbl_bars.setText(str(len(close_list)))

            # Timestamp
            if self._lbl_timestamp is not None:
                self._lbl_timestamp.setText(datetime.now().strftime("%H:%M:%S"))

            # Active strategy - new in database version
            if self._lbl_strategy is not None:
                try:
                    if safe_hasattr(self.trading_app, "detector") and \
                       safe_hasattr(self.trading_app.detector, "signal_engine") and \
                       self.trading_app.detector.signal_engine is not None:
                        engine = self.trading_app.detector.signal_engine
                        strategy_slug = safe_getattr(engine, "strategy_slug", None)
                        if strategy_slug:
                            self._lbl_strategy.setText(strategy_slug)
                            if strategy_slug != self._current_strategy_slug:
                                self._current_strategy_slug = strategy_slug
                        else:
                            self._lbl_strategy.setText("Default")
                    else:
                        self._lbl_strategy.setText("—")
                except Exception as e:
                    logger.debug(f"Failed to get strategy slug: {e}")
                    self._lbl_strategy.setText("—")

            # ── Fired pills ──────────────────────────────────────────────────
            fired_map = option_signal.get("fired", {})
            signal_colors = _get_signal_colors()
            for sig, pill in self._fired_pills.items():
                try:
                    is_fired = fired_map.get(sig, False)
                    color = signal_colors.get(sig, c.TEXT_DISABLED) if is_fired else c.TEXT_DISABLED
                    pill.setStyleSheet(f"""
                        QLabel {{
                            color: {color};
                            border: 2px solid {color if is_fired else c.BORDER};
                            border-radius: {self._sp.RADIUS_SM}px;
                            font-size: {ty.SIZE_XS}pt;
                            font-weight: {ty.WEIGHT_BOLD};
                            background: {color}22 if is_fired else transparent;
                            padding: {self._sp.PAD_XS}px;
                        }}
                    """)
                except Exception as e:
                    logger.warning(f"Failed to update pill for {sig}: {e}")
                    continue

            # ── Group panels ─────────────────────────────────────────────────
            rule_results = option_signal.get("rule_results", {})

            # FEATURE 3: Get confidence scores
            confidence_dict = option_signal.get("confidence", {})
            explanation = option_signal.get("explanation", "")
            threshold = option_signal.get("threshold", 0.6)

            # Store for other tabs
            self._last_confidence = confidence_dict
            self._last_threshold = threshold

            # Try to get engine's indicator cache for richer display
            indicator_cache = {}
            try:
                if safe_hasattr(self.trading_app, "detector") and \
                        safe_hasattr(self.trading_app.detector, "signal_engine") and \
                        self.trading_app.detector.signal_engine is not None:
                    engine = self.trading_app.detector.signal_engine
                    # Access last cache if stored
                    indicator_cache = safe_getattr(engine, "_last_cache", {})
            except Exception as e:
                logger.debug(f"Failed to get indicator cache: {e}")

            for sig in SIGNAL_GROUPS:
                try:
                    if sig not in self._group_panels:
                        continue
                    panel = self._group_panels[sig]
                    rules_for_sig = rule_results.get(sig, [])
                    is_fired = fired_map.get(sig, False)
                    logic = "AND"
                    enabled = True
                    confidence = confidence_dict.get(sig, 0.0)

                    try:
                        engine = safe_getattr(
                            safe_getattr(self.trading_app, "detector", None),
                            "signal_engine", None
                        )
                        if engine is not None:
                            logic = engine.get_logic(sig)
                            enabled = engine.is_enabled(sig)
                    except Exception as e:
                        logger.debug(f"Failed to get engine settings for {sig}: {e}")

                    panel.update(rules_for_sig, is_fired, logic, enabled,
                                confidence, threshold, indicator_cache)

                except Exception as e:
                    logger.warning(f"Failed to update group panel for {sig}: {e}")
                    continue

            # ── Indicator values tab ─────────────────────────────────────────
            # Prefer the pre-computed indicator_values dict emitted by evaluate()
            indicator_values = option_signal.get("indicator_values", {})
            if self._cache_panel is not None:
                try:
                    if indicator_values:
                        self._cache_panel.update_from_values(indicator_values)
                    else:
                        # Fallback: old raw-cache path for backwards compatibility
                        self._cache_panel.update_cache(indicator_cache)
                except Exception as e:
                    logger.warning(f"Failed to update cache panel: {e}")

            # FEATURE 3: Update confidence panel
            if self._confidence_panel is not None:
                try:
                    self._confidence_panel.update_confidence(confidence_dict, threshold, explanation)
                except Exception as e:
                    logger.warning(f"Failed to update confidence panel: {e}")

            # ── Raw JSON tab ─────────────────────────────────────────────────
            if self._json_panel is not None:
                try:
                    self._json_panel.update_result(option_signal)
                except Exception as e:
                    logger.warning(f"Failed to update JSON panel: {e}")

            if self._status_lbl is not None:
                self._status_lbl.setText(f"✓  Last update: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            logger.error(f"DynamicSignalDebugPopup.refresh error: {e}", exc_info=True)
            if self._status_lbl is not None:
                self._status_lbl.setText(f"⚠  Refresh error: {e}")

    def closeEvent(self, event):
        """Handle close event with cleanup - Rule 7"""
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)

    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            if self._timer and self._timer.isActive():
                self._timer.stop()
            self._timer = None
            self.trading_app = None
            logger.info("[DynamicSignalDebugPopup] Cleanup completed")
        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup.cleanup] Error: {e}", exc_info=True)