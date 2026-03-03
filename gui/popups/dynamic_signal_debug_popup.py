"""
dynamic_signal_debug_popup_db.py
=================================
A live-updating popup that shows every detail of the DynamicSignalEngine
evaluation: indicator values, rule-by-rule results, group fired/not-fired
status, conflict detection, confidence scores, and the final resolved signal.
Works with database-backed signal engine.

UPDATED: Now uses state_manager instead of direct state access.
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

from __future__ import annotations
import logging
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QLinearGradient
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QGroupBox,
    QGridLayout, QTabWidget, QTextEdit, QProgressBar,
)

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
        lbl.setStyleSheet(f"color: {color}; font-size: {size}pt; font-weight: {ty.WEIGHT_BOLD};")
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
            self.setMinimumWidth(130)
            self.setFixedHeight(36)
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
                    border: {self._sp.SEPARATOR}px solid {color};
                    border-radius: {self._sp.RADIUS_MD}px;
                    font-size: {self._ty.SIZE_LG}pt;
                    font-weight: {self._ty.WEIGHT_BOLD};
                    padding: {self._sp.PAD_XS}px {self._sp.PAD_MD}px;
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


class _ConfidenceBar(QLabel, ThemedMixin):
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

            self.setFixedHeight(16)
            self.setMinimumWidth(80)
            self.apply_theme()
        except Exception as e:
            logger.error(f"[_ConfidenceBar.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        pass

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors"""
        try:
            # Will be updated when set_confidence is called
            pass
        except Exception as e:
            logger.error(f"[_ConfidenceBar.apply_theme] Failed: {e}", exc_info=True)

    def set_confidence(self, confidence: float, threshold: float = 0.6):
        """
        Set confidence value (0.0 to 1.0) and threshold.
        """
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            percent = int(confidence * 100)
            threshold_pct = int(threshold * 100)

            # Color based on confidence relative to threshold
            if confidence >= threshold:
                color = c.GREEN
            elif confidence >= threshold * 0.7:
                color = c.YELLOW
            else:
                color = c.RED

            self.setStyleSheet(f"""
                QLabel {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_XS}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    padding: {sp.PAD_XS}px {sp.PAD_XS}px;
                }}
            """)

            # Create bar using Unicode block characters
            bar_length = 20
            filled = int(percent * bar_length / 100)
            bar = "█" * filled + "░" * (bar_length - filled)

            self.setText(f"{bar}  {percent}% (threshold: {threshold_pct}%)")

        except Exception as e:
            logger.error(f"[_ConfidenceBar.set_confidence] Failed: {e}", exc_info=True)


class _GroupPanel(QGroupBox, ThemedMixin):
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
            super().__init__(f" {label} ", parent)
            self.signal = signal

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._signal_colors = _get_signal_colors()
            self._color = self._signal_colors.get(signal, self._c.TEXT_DISABLED)
            self._setup_ui()
            self.apply_theme()
        except Exception as e:
            logger.error(f"[_GroupPanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(f" {signal} ", parent)
            self.signal = signal
            self._color = self._c.TEXT_DISABLED

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.signal = ""
        self._color = None
        self._logic_lbl = None
        self._fired_lbl = None
        self._enabled_lbl = None
        self._confidence_lbl = None
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
                    QTableWidget {{ alternate-background-color: {c.BG_ROW_B}; background: {c.BG_ROW_A}; }}
                """)

            # Update no rules label
            if self._no_rules_lbl:
                self._no_rules_lbl.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-size: {self._ty.SIZE_XS}pt; padding: {sp.PAD_SM}px;")

        except Exception as e:
            logger.error(f"[_GroupPanel.apply_theme] Failed: {e}", exc_info=True)

    def _setup_ui(self):
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            root = QVBoxLayout(self)
            root.setContentsMargins(sp.PAD_SM, sp.PAD_MD, sp.PAD_SM, sp.PAD_SM)
            root.setSpacing(sp.GAP_XS)

            # Top row: logic + fired indicator + confidence
            top = QHBoxLayout()
            top.setSpacing(sp.GAP_MD)

            self._logic_lbl = _header_label("Logic: AND", "TEXT_DIM")
            top.addWidget(self._logic_lbl)
            top.addStretch()

            # FEATURE 3: Confidence display
            confidence_container = QHBoxLayout()
            self._confidence_lbl = _header_label("Confidence:", "TEXT_DIM", "SIZE_XS")
            self._confidence_bar = _ConfidenceBar()
            confidence_container.addWidget(self._confidence_lbl)
            confidence_container.addWidget(self._confidence_bar)
            top.addLayout(confidence_container)

            top.addStretch()

            self._fired_lbl = QLabel("⬤  NOT FIRED")
            self._fired_lbl.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")
            top.addWidget(self._fired_lbl)

            self._enabled_lbl = QLabel("enabled")
            self._enabled_lbl.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt;")
            top.addWidget(self._enabled_lbl)

            root.addLayout(top)

            # Rule table
            self._table = QTableWidget(0, 5)
            self._table.setHorizontalHeaderLabels(["Rule Expression", "LHS Value", "Op", "RHS Value", "Result"])
            self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            for i in range(1, 5):
                self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
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

            # Enabled
            if self._enabled_lbl is not None:
                if enabled:
                    self._enabled_lbl.setText("✓ enabled")
                    self._enabled_lbl.setStyleSheet(f"color: {c.GREEN}; font-size: {ty.SIZE_XS}pt;")
                else:
                    self._enabled_lbl.setText("✗ disabled")
                    self._enabled_lbl.setStyleSheet(f"color: {c.RED}; font-size: {ty.SIZE_XS}pt;")

            # Fired
            if self._fired_lbl is not None:
                if fired:
                    self._fired_lbl.setText("⬤  FIRED")
                    self._fired_lbl.setStyleSheet(f"color: {self._color}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")
                else:
                    self._fired_lbl.setText("⬤  NOT FIRED")
                    self._fired_lbl.setStyleSheet(f"color: {c.TEXT_DISABLED}; font-size: {ty.SIZE_XS}pt; font-weight: {ty.WEIGHT_BOLD};")

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


class _IndicatorCachePanel(QWidget, ThemedMixin):
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
            layout.setContentsMargins(self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS)

            lbl = _header_label("All computed indicator values during last evaluation:", "TEXT_DIM")
            layout.addWidget(lbl)

            self._table = QTableWidget(0, 3)
            self._table.setHorizontalHeaderLabels(["Indicator (cache key)", "Latest Value", "Prev Value"])
            self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
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
            if self._table:
                self._table.setStyleSheet(f"""
                    QTableWidget {{ alternate-background-color: {c.BG_ROW_B}; background: {c.BG_ROW_A}; }}
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


class _ConfidencePanel(QWidget, ThemedMixin):
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
            header = _header_label("Signal Group Confidence Scores", "BLUE", "SIZE_MD")
            layout.addWidget(header)

            # Explanation label
            self._explanation_lbl = QLabel("No signal evaluation yet")
            self._explanation_lbl.setWordWrap(True)
            layout.addWidget(self._explanation_lbl)

            # Confidence bars for each group
            self._confidence_bars = {}
            for sig in SIGNAL_GROUPS:
                group_box = QGroupBox(SIGNAL_LABELS.get(sig, sig))
                group_layout = QVBoxLayout(group_box)

                # Confidence bar
                bar_layout = QHBoxLayout()
                bar_layout.addWidget(QLabel("Confidence:"))
                bar = _ConfidenceBar()
                bar.set_confidence(0.0)
                bar_layout.addWidget(bar)
                group_layout.addLayout(bar_layout)

                # Threshold line
                threshold_layout = QHBoxLayout()
                threshold_layout.addWidget(QLabel("Threshold:"))
                self._threshold_lbl = QLabel("0.60")
                threshold_layout.addWidget(self._threshold_lbl)
                threshold_layout.addStretch()
                group_layout.addLayout(threshold_layout)

                layout.addWidget(group_box)
                self._confidence_bars[sig] = bar

            layout.addStretch()
            self.apply_theme()

        except Exception as e:
            logger.error(f"[_ConfidencePanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self._explanation_lbl = None
        self._threshold_lbl = None
        self._confidence_bars = {}

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the panel"""
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            if self._explanation_lbl:
                self._explanation_lbl.setStyleSheet(f"""
                    color: {c.TEXT_DIM};
                    font-size: {ty.SIZE_XS}pt;
                    padding: {sp.PAD_SM}px;
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                """)

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


class _RawJsonPanel(QTextEdit, ThemedMixin):
    """Tab showing the raw evaluate() result dict as JSON."""

    def __init__(self, parent=None):
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.setReadOnly(True)
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

            self.setStyleSheet(f"""
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
                self.setPlainText("No data available")
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
            self.setPlainText(text)
        except Exception as e:
            logger.error(f"[_RawJsonPanel.update_result] Failed: {e}", exc_info=True)
            self.setPlainText(f"Error updating: {e}")


class DynamicSignalDebugPopup(QDialog, ThemedMixin):
    """
    Non-modal popup that lives alongside the main TradingGUI window.
    Call refresh() every second (or from _tick_fast) to keep it live.
    Works with database-backed signal engine.
    FEATURE 3: Added confidence display tab.
    UPDATED: Now uses state_manager for state access.
    FULLY INTEGRATED with ThemeManager for dynamic theming.
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
            self.setWindowTitle("🔬 Dynamic Signal Engine — Live Debug")
            self.resize(980, 750)
            self.setMinimumSize(700, 500)

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
            # Still try to create basic dialog
            super().__init__(parent, Qt.Window)
            self.trading_app = trading_app
            self.setWindowTitle("Signal Debug - ERROR")
            self.setMinimumSize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize debug popup:\n{e}")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)

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

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the dialog.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            sp = self._sp

            # Apply main stylesheet
            self.setStyleSheet(self._get_stylesheet())

            # Update all child widgets that have apply_theme methods
            if self._signal_badge and hasattr(self._signal_badge, 'apply_theme'):
                self._signal_badge.apply_theme()

            if self._cache_panel and hasattr(self._cache_panel, 'apply_theme'):
                self._cache_panel.apply_theme()

            if self._confidence_panel and hasattr(self._confidence_panel, 'apply_theme'):
                self._confidence_panel.apply_theme()

            if self._json_panel and hasattr(self._json_panel, 'apply_theme'):
                self._json_panel.apply_theme()

            for panel in self._group_panels.values():
                if hasattr(panel, 'apply_theme'):
                    panel.apply_theme()

            # Update status label style
            if self._status_lbl:
                self._status_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")

            logger.debug("[DynamicSignalDebugPopup.apply_theme] Applied theme")

        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup.apply_theme] Failed: {e}", exc_info=True)

    def _get_stylesheet(self) -> str:
        """Generate stylesheet with current theme tokens"""
        c = self._c
        ty = self._ty
        sp = self._sp

        return f"""
            QDialog, QWidget {{
                background: {c.BG_MAIN};
                color: {c.TEXT_MAIN};
                font-family: '{ty.FONT_MONO}';
            }}
            QLabel {{ color: {c.TEXT_MAIN}; }}
            QGroupBox {{
                background: {c.BG_PANEL};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin-top: {sp.PAD_MD}px;
                padding: {sp.PAD_XS}px;
                font-weight: {ty.WEIGHT_BOLD};
                font-size: {ty.SIZE_SM}pt;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {sp.PAD_MD}px;
                padding: 0 {sp.PAD_XS}px;
                color: {c.TEXT_MAIN};
            }}
            QTableWidget {{
                background: {c.BG_PANEL};
                gridline-color: {c.BORDER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_XS}pt;
            }}
            QTableWidget::item {{ padding: {sp.PAD_XS}px {sp.PAD_SM}px; }}
            QHeaderView::section {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DIM};
                border: none;
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                font-size: {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton {{
                background: {c.BG_HOVER};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_XS}pt;
            }}
            QPushButton:hover {{ background: {c.BORDER}; }}
            QTabWidget::pane {{
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                background: {c.BG_PANEL};
            }}
            QTabBar::tab {{
                background: {c.BG_HOVER};
                color: {c.TEXT_DIM};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-bottom: none;
                border-radius: {sp.RADIUS_SM}px {sp.RADIUS_SM}px 0 0;
                padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                font-size: {ty.SIZE_XS}pt;
            }}
            QTabBar::tab:selected {{
                background: {c.BG_PANEL};
                color: {c.TEXT_MAIN};
                border-bottom: {sp.PAD_XS}px solid {c.BLUE};
            }}
            QScrollArea {{ border: none; background: transparent; }}
            QCheckBox {{ color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; spacing: {sp.GAP_XS}px; }}
        """

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        try:
            c = self._c
            sp = self._sp

            root = QVBoxLayout(self)
            root.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
            root.setSpacing(sp.GAP_SM)

            # ── Header ────────────────────────────────────────────────────────────
            header = self._build_header()
            root.addWidget(header)

            # ── Tabs ─────────────────────────────────────────────────────────────
            self._tabs = QTabWidget()
            root.addWidget(self._tabs, 1)

            # Tab 1: Group panels
            groups_widget = self._build_groups_tab()
            self._tabs.addTab(groups_widget, "📋  Signal Groups")

            # Tab 2: Indicator cache
            self._cache_panel = _IndicatorCachePanel()
            self._tabs.addTab(self._cache_panel, "📊  Indicator Values")

            # FEATURE 3: Confidence tab
            self._confidence_panel = _ConfidencePanel()
            self._tabs.addTab(self._confidence_panel, "📈  Confidence Scores")

            # Tab 3: Raw JSON
            self._json_panel = _RawJsonPanel()
            self._tabs.addTab(self._json_panel, "{}  Raw JSON")

            # ── Footer ───────────────────────────────────────────────────────────
            footer = self._build_footer()
            root.addWidget(footer)

        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup._build_ui] Failed: {e}", exc_info=True)
            raise

    def _build_header(self) -> QWidget:
        try:
            c = self._c
            sp = self._sp

            frame = QFrame()
            frame.setStyleSheet(f"QFrame {{ background: {c.BG_PANEL}; border: {sp.SEPARATOR}px solid {c.BORDER}; border-radius: {sp.RADIUS_MD}px; }}")
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
            layout.setSpacing(sp.GAP_XL)

            # Signal badge (large)
            sig_col = QVBoxLayout()
            sig_col.addWidget(_header_label("FINAL SIGNAL", "TEXT_DIM", "SIZE_XS"))
            self._signal_badge = _SignalBadge()
            sig_col.addWidget(self._signal_badge)
            layout.addLayout(sig_col)

            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setStyleSheet(f"QFrame {{ border: {sp.SEPARATOR}px solid {c.BORDER}; }}")
            layout.addWidget(sep)

            # Grid of quick-status labels
            grid = QGridLayout()
            grid.setHorizontalSpacing(sp.PAD_XL)
            grid.setVerticalSpacing(sp.GAP_XS)

            self._lbl_conflict = self._make_status_pair(grid, 0, 0, "CONFLICT")
            self._lbl_available = self._make_status_pair(grid, 0, 2, "RULES AVAILABLE")
            self._lbl_symbol = self._make_status_pair(grid, 1, 0, "SYMBOL")
            self._lbl_last_close = self._make_status_pair(grid, 1, 2, "LAST CLOSE")
            self._lbl_bars = self._make_status_pair(grid, 2, 0, "BARS IN DF")
            self._lbl_timestamp = self._make_status_pair(grid, 2, 2, "LAST REFRESH")
            self._lbl_strategy = self._make_status_pair(grid, 3, 0, "ACTIVE STRATEGY")

            layout.addLayout(grid, 1)
            layout.addStretch()

            # Fired group indicators (5 small pills)
            fired_col = QVBoxLayout()
            fired_col.addWidget(_header_label("GROUP FIRED", "TEXT_DIM", "SIZE_XS"))
            fired_inner = QHBoxLayout()
            self._fired_pills = {}
            for sig in SIGNAL_GROUPS:
                lbl = QLabel(sig.replace("_", "\n"))
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setFixedSize(64, 42)
                self._fired_pills[sig] = lbl
                fired_inner.addWidget(lbl)
            fired_col.addLayout(fired_inner)
            layout.addLayout(fired_col)

            return frame

        except Exception as e:
            logger.error(f"[_build_header] Failed: {e}", exc_info=True)
            return QFrame()

    def _make_status_pair(self, grid: QGridLayout, row: int, col: int, title: str) -> QLabel:
        try:
            grid.addWidget(_header_label(title, "TEXT_DIM", "SIZE_XS"), row, col)
            val_lbl = _value_label("—", "TEXT_MAIN", "SIZE_XS")
            grid.addWidget(val_lbl, row, col + 1)
            return val_lbl
        except Exception as e:
            logger.error(f"[_make_status_pair] Failed: {e}", exc_info=True)
            lbl = QLabel("—")
            return lbl

    def _build_groups_tab(self) -> QScrollArea:
        try:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            container = QWidget()
            self._groups_layout = QVBoxLayout(container)
            self._groups_layout.setContentsMargins(self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS, self._sp.PAD_XS)
            self._groups_layout.setSpacing(self._sp.GAP_SM)

            self._group_panels = {}
            for sig in SIGNAL_GROUPS:
                panel = _GroupPanel(sig)
                self._group_panels[sig] = panel
                self._groups_layout.addWidget(panel)

            self._groups_layout.addStretch()
            scroll.setWidget(container)
            return scroll

        except Exception as e:
            logger.error(f"[_build_groups_tab] Failed: {e}", exc_info=True)
            scroll = QScrollArea()
            container = QWidget()
            layout = QVBoxLayout(container)
            error_lbl = QLabel(f"Error building groups tab: {e}")
            layout.addWidget(error_lbl)
            scroll.setWidget(container)
            return scroll

    def _build_footer(self) -> QWidget:
        try:
            c = self._c
            sp = self._sp

            frame = QFrame()
            frame.setStyleSheet(f"QFrame {{ background: {c.BG_PANEL}; border: {sp.SEPARATOR}px solid {c.BORDER}; border-radius: {sp.RADIUS_SM}px; }}")
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(sp.PAD_MD, sp.PAD_XS, sp.PAD_MD, sp.PAD_XS)
            layout.setSpacing(sp.GAP_MD)

            self._auto_chk = QCheckBox("Auto-refresh (1 s)")
            self._auto_chk.setChecked(True)
            self._auto_chk.toggled.connect(self._on_auto_toggle)
            layout.addWidget(self._auto_chk)

            layout.addStretch()

            self._status_lbl = QLabel("Waiting for data…")
            self._status_lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {self._ty.SIZE_XS}pt;")
            layout.addWidget(self._status_lbl)

            layout.addStretch()

            refresh_btn = QPushButton("⟳  Refresh Now")
            refresh_btn.clicked.connect(self.refresh)
            layout.addWidget(refresh_btn)

            close_btn = QPushButton("✕  Close")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)

            return frame

        except Exception as e:
            logger.error(f"[_build_footer] Failed: {e}", exc_info=True)
            return QFrame()

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
            trend_data = getattr(state, "derivative_trend", None) or {}
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
                self._lbl_conflict.setText("⚠ YES" if conflict else "No")
                self._lbl_conflict.setStyleSheet(f"color: {c.RED if conflict else c.GREEN}; font-weight: {ty.WEIGHT_BOLD}; font-size: {ty.SIZE_XS}pt;")

            if self._lbl_available is not None:
                self._lbl_available.setText("Yes")
                self._lbl_available.setStyleSheet(f"color: {c.GREEN}; font-weight: {ty.WEIGHT_BOLD}; font-size: {ty.SIZE_XS}pt;")

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
                    if hasattr(self.trading_app, "detector") and \
                       hasattr(self.trading_app.detector, "signal_engine") and \
                       self.trading_app.detector.signal_engine is not None:
                        engine = self.trading_app.detector.signal_engine
                        strategy_slug = getattr(engine, "strategy_slug", None)
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
                            background: {color}33;
                            color: {color};
                            border: {self._sp.SEPARATOR}px solid {color};
                            border-radius: {self._sp.RADIUS_SM}px;
                            font-size: {ty.SIZE_XS}pt;
                            font-weight: {ty.WEIGHT_BOLD};
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
                if hasattr(self.trading_app, "detector") and \
                        hasattr(self.trading_app.detector, "signal_engine") and \
                        self.trading_app.detector.signal_engine is not None:
                    engine = self.trading_app.detector.signal_engine
                    # Access last cache if stored
                    indicator_cache = getattr(engine, "_last_cache", {})
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
                        engine = getattr(
                            getattr(self.trading_app, "detector", None),
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