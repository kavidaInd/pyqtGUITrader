"""
DynamicSignalDebugPopup
=======================
A live-updating popup that shows every detail of the DynamicSignalEngine
evaluation: indicator values, rule-by-rule results, group fired/not-fired
status, conflict detection, and the final resolved signal.

Usage (from TradingGUI.py):
    # In __init__:
    self.signal_debug_popup = None

    # In _create_menu (under the View menu):
    sig_act = QAction("🔬 Dynamic Signal Debug", self)
    sig_act.triggered.connect(self._show_signal_debug_popup)
    view_menu.addAction(sig_act)

    # New method:
    def _show_signal_debug_popup(self):
        if not self.trading_app:
            QMessageBox.information(self, "Not Ready", "Trading app not initialized yet.")
            return
        if not self.signal_debug_popup:
            self.signal_debug_popup = DynamicSignalDebugPopup(self.trading_app, self)
        self.signal_debug_popup.show()
        self.signal_debug_popup.raise_()
        self.signal_debug_popup.activateWindow()

    # In _tick_fast, add:
    if self.signal_debug_popup and self.signal_debug_popup.isVisible():
        self.signal_debug_popup.refresh()

    # In _close_all_popups, add:
    if self.signal_debug_popup:
        self.signal_debug_popup.close()
"""

from __future__ import annotations
import logging
import logging.handlers
import json
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QGroupBox,
    QGridLayout, QTabWidget, QTextEdit,
)

# Rule 4: Structured logging
logger = logging.getLogger(__name__)

# ── Colours matching the dark theme ─────────────────────────────────────────
BG_MAIN = "#0d1117"
BG_PANEL = "#161b22"
BG_ROW_A = "#1c2128"
BG_ROW_B = "#22272e"
BORDER = "#30363d"
TEXT_DIM = "#8b949e"
TEXT_MAIN = "#e6edf3"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d29922"
BLUE = "#58a6ff"
PURPLE = "#bc8cff"
ORANGE = "#ffa657"
GREY_OFF = "#484f58"

SIGNAL_COLORS = {
    "BUY_CALL": "#3fb950",
    "BUY_PUT": "#58a6ff",
    "EXIT_CALL": "#f85149",
    "EXIT_PUT": "#ffa657",
    "HOLD": "#d29922",
    "WAIT": "#484f58",
}

SIGNAL_LABELS = {
    "BUY_CALL": "📈  Buy Call",
    "BUY_PUT": "📉  Buy Put",
    "EXIT_CALL": "🔴  Exit Call",
    "EXIT_PUT": "🟠  Exit Put",
    "HOLD": "⏸   Hold",
    "WAIT": "⏳  Wait",
}

SIGNAL_GROUPS = ["BUY_CALL", "BUY_PUT", "EXIT_CALL", "EXIT_PUT", "HOLD"]


def _style_sheet() -> str:
    return f"""
        QDialog, QWidget {{
            background: {BG_MAIN};
            color: {TEXT_MAIN};
            font-family: 'Consolas', 'Menlo', monospace;
        }}
        QLabel {{ color: {TEXT_MAIN}; }}
        QGroupBox {{
            background: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 6px;
            margin-top: 12px;
            padding: 6px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {TEXT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget {{
            background: {BG_PANEL};
            gridline-color: {BORDER};
            border: 1px solid {BORDER};
            border-radius: 4px;
            color: {TEXT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget::item {{ padding: 4px 8px; }}
        QHeaderView::section {{
            background: #21262d;
            color: {TEXT_DIM};
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 4px 8px;
            font-size: 8pt;
            font-weight: bold;
        }}
        QPushButton {{
            background: #21262d;
            color: {TEXT_MAIN};
            border: 1px solid {BORDER};
            border-radius: 5px;
            padding: 6px 16px;
            font-size: 9pt;
        }}
        QPushButton:hover {{ background: #2d333b; }}
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 4px;
            background: {BG_PANEL};
        }}
        QTabBar::tab {{
            background: #21262d;
            color: {TEXT_DIM};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-radius: 4px 4px 0 0;
            padding: 5px 14px;
            font-size: 9pt;
        }}
        QTabBar::tab:selected {{
            background: {BG_PANEL};
            color: {TEXT_MAIN};
            border-bottom: 2px solid {BLUE};
        }}
        QScrollArea {{ border: none; background: transparent; }}
        QCheckBox {{ color: {TEXT_DIM}; font-size: 9pt; spacing: 5px; }}
        QTextEdit {{
            background: {BG_PANEL};
            color: {TEXT_MAIN};
            border: 1px solid {BORDER};
            border-radius: 4px;
            font-family: 'Consolas', 'Menlo', monospace;
            font-size: 9pt;
        }}
    """


def _header_label(text: str, color: str = TEXT_DIM, size: int = 8) -> QLabel:
    try:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: {size}pt; font-weight: bold;")
        return lbl
    except Exception as e:
        logger.error(f"[_header_label] Failed: {e}", exc_info=True)
        lbl = QLabel(text)
        return lbl


def _value_label(text: str, color: str = TEXT_MAIN, size: int = 9) -> QLabel:
    try:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color}; font-size: {size}pt; font-weight: bold;")
        return lbl
    except Exception as e:
        logger.error(f"[_value_label] Failed: {e}", exc_info=True)
        lbl = QLabel(text)
        return lbl


class _SignalBadge(QLabel):
    """Pill-shaped label showing a signal value."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.setAlignment(Qt.AlignCenter)
            self.setMinimumWidth(130)
            self.setFixedHeight(36)
            self._set("WAIT")
        except Exception as e:
            logger.error(f"[_SignalBadge.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)
            self.setAlignment(Qt.AlignCenter)
            self.setText("ERROR")

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._last_signal = "WAIT"

    def _set(self, signal_value: str):
        try:
            color = SIGNAL_COLORS.get(signal_value, SIGNAL_COLORS["WAIT"])
            label = SIGNAL_LABELS.get(signal_value, signal_value)
            self.setText(label)
            self.setStyleSheet(f"""
                QLabel {{
                    background: {color}22;
                    color: {color};
                    border: 2px solid {color};
                    border-radius: 6px;
                    font-size: 13pt;
                    font-weight: bold;
                    padding: 2px 12px;
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
    """One row in a rule table: rule expression | current values | result."""

    def __init__(self, table: QTableWidget, row: int):
        try:
            self.table = table
            self.row = row
        except Exception as e:
            logger.error(f"[_RuleRow.__init__] Failed: {e}", exc_info=True)

    def set(self, rule_str: str, lhs_val: str, op: str, rhs_val: str, result: bool,
            error: str = "", is_blocker: bool = False):
        try:
            # Annotate the rule expression with a BLOCKER tag when it is the
            # first False rule in an AND chain that prevents the group firing.
            display_rule = f"⚠ {rule_str}  [► BLOCKER]" if is_blocker else rule_str

            items = [
                (display_rule, YELLOW if is_blocker else TEXT_MAIN),
                (lhs_val, BLUE),
                (op, YELLOW),
                (rhs_val, ORANGE),
                ("✅  TRUE" if result else "❌  FALSE", GREEN if result else RED),
            ]
            if error:
                items[-1] = (f"⚠ {error[:40]}", YELLOW)

            for col, (text, color) in enumerate(items):
                item = QTableWidgetItem(str(text) if text is not None else "")
                item.setForeground(QColor(color))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if is_blocker:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QColor(RED + "18"))
                self.table.setItem(self.row, col, item)

        except Exception as e:
            logger.error(f"[_RuleRow.set] Failed: {e}", exc_info=True)


class _GroupPanel(QGroupBox):
    """
    Panel for one signal group (BUY_CALL, BUY_PUT, etc.).
    Shows logic mode, fired status, and a per-rule table.
    """

    def __init__(self, signal: str, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            label = SIGNAL_LABELS.get(signal, signal)
            color = SIGNAL_COLORS.get(signal, GREY_OFF)
            super().__init__(f" {label} ", parent)
            self.signal = signal
            self._color = color
            self._setup_ui()
        except Exception as e:
            logger.error(f"[_GroupPanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(f" {signal} ", parent)
            self.signal = signal
            self._color = GREY_OFF

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.signal = ""
        self._color = GREY_OFF
        self._logic_lbl = None
        self._fired_lbl = None
        self._enabled_lbl = None
        self._table = None
        self._no_rules_lbl = None

    def _setup_ui(self):
        try:
            root = QVBoxLayout(self)
            root.setContentsMargins(8, 12, 8, 8)
            root.setSpacing(6)

            # Top row: logic + fired indicator
            top = QHBoxLayout()
            top.setSpacing(10)

            self._logic_lbl = _header_label("Logic: AND", TEXT_DIM)
            top.addWidget(self._logic_lbl)
            top.addStretch()

            self._fired_lbl = QLabel("⬤  NOT FIRED")
            self._fired_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 9pt; font-weight: bold;")
            top.addWidget(self._fired_lbl)

            self._enabled_lbl = QLabel("enabled")
            self._enabled_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 8pt;")
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
            self._table.setStyleSheet(f"""
                QTableWidget {{ alternate-background-color: {BG_ROW_B}; background: {BG_ROW_A}; }}
            """)
            self._table.setMinimumHeight(80)
            self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            root.addWidget(self._table)

            self._no_rules_lbl = QLabel("  ⚪ No rules configured for this signal.")
            self._no_rules_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 9pt; padding: 8px;")
            root.addWidget(self._no_rules_lbl)
            self._no_rules_lbl.hide()

        except Exception as e:
            logger.error(f"[_GroupPanel._setup_ui] Failed: {e}", exc_info=True)

    def update(self, rule_results: List[Dict], fired: bool, logic: str, enabled: bool,
               indicator_cache: Dict = None):
        try:
            # Logic label
            if self._logic_lbl is not None:
                self._logic_lbl.setText(f"Logic: {logic}")

            # Enabled
            if self._enabled_lbl is not None:
                if enabled:
                    self._enabled_lbl.setText("✓ enabled")
                    self._enabled_lbl.setStyleSheet(f"color: {GREEN}; font-size: 8pt;")
                else:
                    self._enabled_lbl.setText("✗ disabled")
                    self._enabled_lbl.setStyleSheet(f"color: {RED}; font-size: 8pt;")

            # Fired
            if self._fired_lbl is not None:
                if fired:
                    self._fired_lbl.setText("⬤  FIRED")
                    self._fired_lbl.setStyleSheet(f"color: {self._color}; font-size: 9pt; font-weight: bold;")
                else:
                    self._fired_lbl.setText("⬤  NOT FIRED")
                    self._fired_lbl.setStyleSheet(f"color: {GREY_OFF}; font-size: 9pt; font-weight: bold;")

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
                    for _op in ["crosses_above", "crosses_below", ">=", "<=", "!=", "==", ">", "<"]:
                        if f" {_op} " in rule_str:
                            op = _op
                            break

                    _RuleRow(self._table, i).set(rule_str, lhs_val, op, rhs_val, result, error, is_blocker)

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

        OPERATORS = ["crosses_above", "crosses_below", ">=", "<=", "!=", "==", ">", "<"]

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


class _IndicatorCachePanel(QWidget):
    """Tab showing raw computed indicator values from the engine cache."""

    def __init__(self, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)

            lbl = _header_label("All computed indicator values during last evaluation:", TEXT_DIM)
            layout.addWidget(lbl)

            self._table = QTableWidget(0, 3)
            self._table.setHorizontalHeaderLabels(["Indicator (cache key)", "Latest Value", "Prev Value"])
            self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self._table.verticalHeader().setVisible(False)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._table.setAlternatingRowColors(True)
            self._table.setStyleSheet(f"""
                QTableWidget {{ alternate-background-color: {BG_ROW_B}; background: {BG_ROW_A}; }}
            """)
            layout.addWidget(self._table)

        except Exception as e:
            logger.error(f"[_IndicatorCachePanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self._table = None

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
            if self._table is None:
                logger.warning("_render_rows called with None table")
                return

            self._table.setRowCount(len(rows))
            for i, (key, latest, prev) in enumerate(rows):
                try:
                    for j, (text, color) in enumerate([(key, TEXT_DIM), (latest, BLUE), (prev, TEXT_DIM)]):
                        item = QTableWidgetItem(str(text) if text is not None else "N/A")
                        item.setForeground(QColor(color))
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        self._table.setItem(i, j, item)
                except Exception as e:
                    logger.warning(f"Failed to render row {i}: {e}")
                    continue
        except Exception as e:
            logger.error(f"[_IndicatorCachePanel._render_rows] Failed: {e}", exc_info=True)


class _RawJsonPanel(QTextEdit):
    """Tab showing the raw evaluate() result dict as JSON."""

    def __init__(self, parent=None):
        try:
            super().__init__(parent)
            self.setReadOnly(True)
        except Exception as e:
            logger.error(f"[_RawJsonPanel.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

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


class DynamicSignalDebugPopup(QDialog):
    """
    Non-modal popup that lives alongside the main TradingGUI window.
    Call  refresh()  every second (or from _tick_fast) to keep it live.
    """

    def __init__(self, trading_app, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent, Qt.Window)
            self.trading_app = trading_app
            self.setWindowTitle("🔬 Dynamic Signal Engine — Live Debug")
            self.resize(980, 750)
            self.setMinimumSize(700, 500)
            self.setStyleSheet(_style_sheet())

            # Internal state
            self._last_signal_value: str = ""
            self._auto_refresh = True
            self._indicator_cache: Dict = {}

            self._build_ui()

            # Auto-refresh every second when visible
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._maybe_refresh)
            self._timer.start(1000)

            logger.info("DynamicSignalDebugPopup initialized")

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
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
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
        self._timer = None
        self._signal_badge = None
        self._lbl_conflict = None
        self._lbl_available = None
        self._lbl_symbol = None
        self._lbl_last_close = None
        self._lbl_bars = None
        self._lbl_timestamp = None
        self._fired_pills = {}
        self._group_panels = {}
        self._cache_panel = None
        self._json_panel = None
        self._tabs = None
        self._status_lbl = None
        self._auto_chk = None

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        try:
            root = QVBoxLayout(self)
            root.setContentsMargins(10, 10, 10, 10)
            root.setSpacing(8)

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
            frame = QFrame()
            frame.setStyleSheet(f"QFrame {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}")
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(16, 10, 16, 10)
            layout.setSpacing(20)

            # Signal badge (large)
            sig_col = QVBoxLayout()
            sig_col.addWidget(_header_label("FINAL SIGNAL", TEXT_DIM, 8))
            self._signal_badge = _SignalBadge()
            sig_col.addWidget(self._signal_badge)
            layout.addLayout(sig_col)

            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setStyleSheet(f"QFrame {{ border: 1px solid {BORDER}; }}")
            layout.addWidget(sep)

            # Grid of quick-status labels
            grid = QGridLayout()
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(4)

            self._lbl_conflict = self._make_status_pair(grid, 0, 0, "CONFLICT")
            self._lbl_available = self._make_status_pair(grid, 0, 2, "RULES AVAILABLE")
            self._lbl_symbol = self._make_status_pair(grid, 1, 0, "SYMBOL")
            self._lbl_last_close = self._make_status_pair(grid, 1, 2, "LAST CLOSE")
            self._lbl_bars = self._make_status_pair(grid, 2, 0, "BARS IN DF")
            self._lbl_timestamp = self._make_status_pair(grid, 2, 2, "LAST REFRESH")

            layout.addLayout(grid, 1)
            layout.addStretch()

            # Fired group indicators (5 small pills)
            fired_col = QVBoxLayout()
            fired_col.addWidget(_header_label("GROUP FIRED", TEXT_DIM, 8))
            fired_inner = QHBoxLayout()
            self._fired_pills = {}
            for sig in SIGNAL_GROUPS:
                lbl = QLabel(sig.replace("_", "\n"))
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setFixedSize(64, 42)
                lbl.setStyleSheet(f"""
                    QLabel {{
                        background: {GREY_OFF}33;
                        color: {GREY_OFF};
                        border: 1px solid {GREY_OFF};
                        border-radius: 5px;
                        font-size: 7pt;
                        font-weight: bold;
                    }}
                """)
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
            grid.addWidget(_header_label(title, TEXT_DIM, 7), row, col)
            val_lbl = _value_label("—", TEXT_MAIN, 9)
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
            self._groups_layout.setContentsMargins(4, 4, 4, 4)
            self._groups_layout.setSpacing(8)

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
            error_lbl.setStyleSheet(f"color: {RED};")
            layout.addWidget(error_lbl)
            scroll.setWidget(container)
            return scroll

    def _build_footer(self) -> QWidget:
        try:
            frame = QFrame()
            frame.setStyleSheet(f"QFrame {{ background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 4px; }}")
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(10, 6, 10, 6)
            layout.setSpacing(10)

            self._auto_chk = QCheckBox("Auto-refresh (1 s)")
            self._auto_chk.setChecked(True)
            self._auto_chk.toggled.connect(self._on_auto_toggle)
            layout.addWidget(self._auto_chk)

            layout.addStretch()

            self._status_lbl = QLabel("Waiting for data…")
            self._status_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
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
        """Pull the latest option_signal from trading_app.state and update UI."""
        try:
            if self.trading_app is None:
                if self._status_lbl is not None:
                    self._status_lbl.setText("⚠  trading_app is None")
                return

            state = getattr(self.trading_app, "state", None)
            if state is None:
                if self._status_lbl is not None:
                    self._status_lbl.setText("⚠  trading_app.state is None")
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
                self._lbl_conflict.setStyleSheet(f"color: {RED if conflict else GREEN}; font-weight: bold; font-size: 9pt;")

            if self._lbl_available is not None:
                self._lbl_available.setText("Yes")
                self._lbl_available.setStyleSheet(f"color: {GREEN}; font-weight: bold; font-size: 9pt;")

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

            # ── Fired pills ──────────────────────────────────────────────────
            fired_map = option_signal.get("fired", {})
            for sig, pill in self._fired_pills.items():
                try:
                    is_fired = fired_map.get(sig, False)
                    color = SIGNAL_COLORS.get(sig, GREY_OFF) if is_fired else GREY_OFF
                    pill.setStyleSheet(f"""
                        QLabel {{
                            background: {color}33;
                            color: {color};
                            border: 2px solid {color};
                            border-radius: 5px;
                            font-size: 7pt;
                            font-weight: bold;
                        }}
                    """)
                except Exception as e:
                    logger.warning(f"Failed to update pill for {sig}: {e}")
                    continue

            # ── Group panels ─────────────────────────────────────────────────
            rule_results = option_signal.get("rule_results", {})

            # Try to get engine's indicator cache for richer display
            indicator_cache = {}
            try:
                if hasattr(self.trading_app, "trend_detector") and \
                        hasattr(self.trading_app.trend_detector, "signal_engine") and \
                        self.trading_app.trend_detector.signal_engine is not None:
                    engine = self.trading_app.trend_detector.signal_engine
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

                    try:
                        engine = getattr(
                            getattr(self.trading_app, "trend_detector", None),
                            "signal_engine", None
                        )
                        if engine is not None:
                            logic = engine.get_logic(sig)
                            enabled = engine.is_enabled(sig)
                    except Exception as e:
                        logger.debug(f"Failed to get engine settings for {sig}: {e}")

                    panel.update(rules_for_sig, is_fired, logic, enabled, indicator_cache)

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
        """Handle close event with cleanup"""
        try:
            if self._timer is not None:
                self._timer.stop()
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"[DynamicSignalDebugPopup.closeEvent] Failed: {e}", exc_info=True)
            super().closeEvent(event)