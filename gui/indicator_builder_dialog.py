"""
IndicatorRuleBuilderDialog — PyQt5 GUI for option trading signal rules.
Tabs: BUY_CALL | BUY_PUT | SELL_CALL | SELL_PUT | HOLD
Each tab: list of rules + add/edit/remove + AND/OR toggle + enable/disable
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QSpinBox,
    QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from strategy.dynamic_signal_engine import (
    INDICATOR_DEFAULTS, INDICATOR_MAP, OHLCV_COLUMNS, OPERATORS,
    SIGNAL_GROUPS, SIGNAL_LABELS, SIGNAL_COLORS,
    DynamicSignalEngine, OptionSignal, _rule_to_string,
)

logger = logging.getLogger(__name__)

# ── Colour palette ─────────────────────────────────────────────────────────
DARK_BG = "#1e1e2e"
PANEL_BG = "#282838"
ACCENT = "#7c9ef8"
GREEN = "#a6e3a1"
RED = "#f38ba8"
BLUE = "#89b4fa"
ORANGE = "#fab387"
YELLOW = "#f9e2af"
TEXT = "#cdd6f4"
MUTED = "#585b70"
BORDER = "#45475a"

STYLE = f"""
QWidget {{ background:{DARK_BG}; color:{TEXT}; font-family:'Segoe UI',Arial; font-size:12px; }}
QTabWidget::pane {{ border:1px solid {BORDER}; border-radius:4px; }}
QTabBar::tab {{ background:{PANEL_BG}; color:{MUTED}; padding:8px 16px; border-radius:4px 4px 0 0; min-width:90px; }}
QTabBar::tab:selected {{ background:{DARK_BG}; color:{ACCENT}; border-bottom:2px solid {ACCENT}; }}
QPushButton {{ background:{PANEL_BG}; color:{TEXT}; border:1px solid {BORDER}; border-radius:4px; padding:6px 14px; }}
QPushButton:hover {{ background:{ACCENT}; color:{DARK_BG}; }}
QPushButton#btn_add {{ background:{GREEN}; color:{DARK_BG}; font-weight:bold; }}
QPushButton#btn_remove {{ background:{RED}; color:{DARK_BG}; font-weight:bold; }}
QPushButton#btn_save {{ background:{ACCENT}; color:{DARK_BG}; font-weight:bold; padding:8px 24px; }}
QListWidget {{ background:{PANEL_BG}; border:1px solid {BORDER}; border-radius:4px; padding:4px; }}
QListWidget::item {{ padding:6px; border-radius:3px; }}
QListWidget::item:selected {{ background:{ACCENT}; color:{DARK_BG}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background:{PANEL_BG}; border:1px solid {BORDER}; border-radius:4px; padding:4px 8px; color:{TEXT}; }}
QGroupBox {{ border:1px solid {BORDER}; border-radius:6px; margin-top:12px; padding:8px; font-weight:bold; color:{ACCENT}; }}
QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; }}
QTextEdit {{ background:{PANEL_BG}; border:1px solid {BORDER}; border-radius:4px; color:{GREEN}; font-family:'Consolas','Courier New',monospace; font-size:11px; }}
QCheckBox {{ color:{TEXT}; spacing:6px; }}
QRadioButton {{ color:{TEXT}; spacing:6px; }}
QLabel#lbl_signal {{ font-size:24px; font-weight:bold; padding:10px 20px; border-radius:8px; }}
"""


# ── Side definition widget ─────────────────────────────────────────────────
class SideWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._param_widgets: List[tuple] = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        self.rb_ind = QRadioButton("Indicator")
        self.rb_col = QRadioButton("Column")
        self.rb_scl = QRadioButton("Scalar")
        self.rb_ind.setChecked(True)
        for rb in (self.rb_ind, self.rb_col, self.rb_scl):
            rb.toggled.connect(self._on_type)
            row.addWidget(rb)
        row.addStretch()
        lay.addLayout(row)

        from PyQt5.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()

        # page 0 – indicator
        p0 = QWidget()
        f0 = QFormLayout(p0)
        f0.setContentsMargins(0, 4, 0, 0);
        f0.setSpacing(6)
        self.cb_ind = QComboBox()
        for k in sorted(INDICATOR_MAP.keys()):
            self.cb_ind.addItem(k.upper(), k)
        self.cb_ind.currentIndexChanged.connect(self._on_ind_changed)
        f0.addRow("Indicator:", self.cb_ind)
        self.params_grp = QGroupBox("Parameters")
        self.params_lay = QFormLayout(self.params_grp)
        self.params_lay.setContentsMargins(8, 12, 8, 8);
        self.params_lay.setSpacing(4)
        f0.addRow(self.params_grp)
        self.stack.addWidget(p0)

        # page 1 – column
        p1 = QWidget()
        f1 = QFormLayout(p1)
        f1.setContentsMargins(0, 4, 0, 0)
        self.cb_col = QComboBox()
        for c in OHLCV_COLUMNS:
            self.cb_col.addItem(c.upper(), c)
        self.cb_col.currentIndexChanged.connect(lambda _: self.changed.emit())
        f1.addRow("Column:", self.cb_col)
        self.stack.addWidget(p1)

        # page 2 – scalar
        p2 = QWidget()
        f2 = QFormLayout(p2)
        f2.setContentsMargins(0, 4, 0, 0)
        self.spin_scl = QDoubleSpinBox()
        self.spin_scl.setRange(-1e9, 1e9);
        self.spin_scl.setDecimals(4)
        self.spin_scl.valueChanged.connect(lambda _: self.changed.emit())
        f2.addRow("Value:", self.spin_scl)
        self.stack.addWidget(p2)

        lay.addWidget(self.stack)
        self._on_ind_changed()

    def _on_type(self):
        self.stack.setCurrentIndex(0 if self.rb_ind.isChecked() else (1 if self.rb_col.isChecked() else 2))
        self.changed.emit()

    def _on_ind_changed(self):
        while self.params_lay.rowCount():
            self.params_lay.removeRow(0)
        self._param_widgets.clear()
        ind = self.cb_ind.currentData() or "rsi"
        for name, default in INDICATOR_DEFAULTS.get(ind, {}).items():
            if isinstance(default, int):
                w = QSpinBox();
                w.setRange(1, 9999);
                w.setValue(default)
                w.valueChanged.connect(lambda _: self.changed.emit())
            else:
                w = QDoubleSpinBox();
                w.setRange(0.001, 9999.0);
                w.setDecimals(3);
                w.setValue(float(default))
                w.valueChanged.connect(lambda _: self.changed.emit())
            self._param_widgets.append((name, w))
            self.params_lay.addRow(f"{name}:", w)
        self.changed.emit()

    def get_def(self):
        if self.rb_ind.isChecked():
            return {"type": "indicator", "indicator": self.cb_ind.currentData(),
                    "params": {n: w.value() for n, w in self._param_widgets}}
        if self.rb_col.isChecked():
            return {"type": "column", "column": self.cb_col.currentData()}
        return {"type": "scalar", "value": self.spin_scl.value()}

    def set_def(self, d):
        t = d.get("type", "indicator")
        if t == "scalar":
            self.rb_scl.setChecked(True);
            self.spin_scl.setValue(float(d.get("value", 0)))
        elif t == "column":
            self.rb_col.setChecked(True)
            idx = self.cb_col.findData(d.get("column", "close"))
            if idx >= 0: self.cb_col.setCurrentIndex(idx)
        else:
            self.rb_ind.setChecked(True)
            idx = self.cb_ind.findData(d.get("indicator", "rsi"))
            if idx >= 0:
                self.cb_ind.setCurrentIndex(idx);
                self._on_ind_changed()
            for name, w in self._param_widgets:
                if name in d.get("params", {}): w.setValue(d["params"][name])


# ── Rule editor dialog ─────────────────────────────────────────────────────
class RuleEditorDialog(QDialog):
    def __init__(self, rule=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rule Editor");
        self.setModal(True)
        self.setMinimumWidth(620);
        self.setStyleSheet(STYLE)
        self._build()
        if rule: self._load(rule)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        title = QLabel("Define Comparison Rule")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(f"color:{ACCENT};")
        lay.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(16)

        for attr, label in (("lhs", "Left Side (LHS)"), ("rhs", "Right Side (RHS)")):
            grp = QGroupBox(label)
            inner = QVBoxLayout(grp)
            w = SideWidget()
            w.changed.connect(self._update_preview)
            setattr(self, attr + "_w", w)
            inner.addWidget(w)
            row.addWidget(grp, stretch=2)
            if attr == "lhs":
                op_grp = QGroupBox("Operator")
                op_inner = QVBoxLayout(op_grp)
                self.cb_op = QComboBox()
                for op in OPERATORS: self.cb_op.addItem(op)
                self.cb_op.currentIndexChanged.connect(self._update_preview)
                op_inner.addWidget(self.cb_op)
                op_inner.addStretch()
                row.addWidget(op_grp, stretch=1)

        lay.addLayout(row)

        lay.addWidget(QLabel("Rule Preview:"))
        self.lbl_prev = QLabel("")
        self.lbl_prev.setObjectName("lbl_preview")
        self.lbl_prev.setWordWrap(True)
        self.lbl_prev.setStyleSheet(
            f"color:{ACCENT}; font-family:'Consolas'; padding:6px; background:{PANEL_BG}; border:1px solid {BORDER}; border-radius:4px;")
        lay.addWidget(self.lbl_prev)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept);
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._update_preview()

    def _update_preview(self):
        try:
            self.lbl_prev.setText(_rule_to_string(self.get_rule()))
        except:
            self.lbl_prev.setText("...")

    def _load(self, rule):
        self.lhs_w.set_def(rule.get("lhs", {}))
        idx = self.cb_op.findText(rule.get("op", ">"))
        if idx >= 0: self.cb_op.setCurrentIndex(idx)
        self.rhs_w.set_def(rule.get("rhs", {}))
        self._update_preview()

    def get_rule(self):
        return {"lhs": self.lhs_w.get_def(), "op": self.cb_op.currentText(), "rhs": self.rhs_w.get_def()}


# ── Signal group panel (one tab) ───────────────────────────────────────────
class SignalGroupPanel(QWidget):
    rules_changed = pyqtSignal()

    def __init__(self, signal: OptionSignal, engine: DynamicSignalEngine, parent=None):
        super().__init__(parent)
        self.signal = signal
        self.engine = engine
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self);
        lay.setSpacing(10)

        top = QHBoxLayout()
        # Enable toggle
        self.chk_enabled = QCheckBox("Enable this signal group")
        self.chk_enabled.setChecked(self.engine.is_enabled(self.signal))
        self.chk_enabled.toggled.connect(self._on_toggle_enable)
        top.addWidget(self.chk_enabled)
        top.addStretch()
        lay.addLayout(top)

        logic_row = QHBoxLayout()
        logic_row.addWidget(QLabel("Combine rules with:"))
        self.rb_and = QRadioButton("AND  (all must pass)")
        self.rb_or = QRadioButton("OR  (any one passes)")
        self.rb_and.setChecked(self.engine.get_logic(self.signal) == "AND")
        self.rb_or.setChecked(self.engine.get_logic(self.signal) == "OR")
        self.rb_and.toggled.connect(self._on_logic)
        logic_row.addWidget(self.rb_and);
        logic_row.addWidget(self.rb_or)
        logic_row.addStretch()
        lay.addLayout(logic_row)

        self.rule_list = QListWidget()
        lay.addWidget(self.rule_list, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("＋  Add Rule");
        self.btn_add.setObjectName("btn_add")
        self.btn_edit = QPushButton("✎  Edit")
        self.btn_remove = QPushButton("✕  Remove");
        self.btn_remove.setObjectName("btn_remove")
        for b in (self.btn_add, self.btn_edit, self.btn_remove): btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_remove.clicked.connect(self._remove)

    def _on_toggle_enable(self, v):
        self.engine.set_enabled(self.signal, v)
        self.rules_changed.emit()

    def _on_logic(self):
        self.engine.set_logic(self.signal, "AND" if self.rb_and.isChecked() else "OR")
        self.rules_changed.emit()

    def _refresh(self):
        self.rule_list.clear()
        color = SIGNAL_COLORS.get(self.signal.value, ACCENT)
        for desc in self.engine.rule_descriptions(self.signal):
            item = QListWidgetItem(f"  {desc}")
            item.setForeground(QColor(color))
            self.rule_list.addItem(item)

    def _add(self):
        dlg = RuleEditorDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.engine.add_rule(self.signal, dlg.get_rule())
            self._refresh();
            self.rules_changed.emit()

    def _edit(self):
        row = self.rule_list.currentRow()
        if row < 0: QMessageBox.information(self, "Edit", "Select a rule first."); return
        rules = self.engine.get_rules(self.signal)
        dlg = RuleEditorDialog(rule=rules[row], parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.engine.update_rule(self.signal, row, dlg.get_rule())
            self._refresh();
            self.rules_changed.emit()

    def _remove(self):
        row = self.rule_list.currentRow()
        if row < 0: QMessageBox.information(self, "Remove", "Select a rule first."); return
        self.engine.remove_rule(self.signal, row)
        self._refresh();
        self.rules_changed.emit()


# ── Main widget ────────────────────────────────────────────────────────────
class IndicatorRuleBuilderWidget(QWidget):
    signals_updated = pyqtSignal(dict)

    def __init__(self, engine: Optional[DynamicSignalEngine] = None, parent=None):
        super().__init__(parent)
        self.engine = engine or DynamicSignalEngine()
        self._test_df = None
        self.setStyleSheet(STYLE)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self);
        lay.setSpacing(12)

        hdr = QLabel("⚡  Option Signal Rule Builder")
        hdr.setFont(QFont("Segoe UI", 15, QFont.Bold))
        hdr.setStyleSheet(f"color:{ACCENT}; padding-bottom:4px;")
        lay.addWidget(hdr)

        sub = QLabel("Configure indicator rules for each option trading signal. Engine resolves to one action per bar.")
        sub.setStyleSheet(f"color:{MUTED};");
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # Conflict resolution
        cr_row = QHBoxLayout()
        cr_row.addWidget(QLabel("When BUY_CALL + BUY_PUT both fire:"))
        self.cb_conflict = QComboBox()
        self.cb_conflict.addItem("Return WAIT (safe)", "WAIT")
        self.cb_conflict.addItem("Prefer BUY_CALL (priority)", "PRIORITY")
        idx = 0 if self.engine.conflict_resolution == "WAIT" else 1
        self.cb_conflict.setCurrentIndex(idx)
        self.cb_conflict.currentIndexChanged.connect(self._on_conflict_changed)
        cr_row.addWidget(self.cb_conflict);
        cr_row.addStretch()
        lay.addLayout(cr_row)

        sep = QFrame();
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{BORDER};");
        lay.addWidget(sep)

        # Signal tabs
        self.tabs = QTabWidget()
        self.panels: Dict[str, SignalGroupPanel] = {}
        for sig in SIGNAL_GROUPS:
            label = SIGNAL_LABELS.get(sig.value, sig.value)
            panel = SignalGroupPanel(sig, self.engine)
            panel.rules_changed.connect(self._on_changed)
            self.panels[sig.value] = panel
            self.tabs.addTab(panel, label)
            # Colour the tab
            color = SIGNAL_COLORS.get(sig.value, ACCENT)
            self.tabs.tabBar().setTabTextColor(self.tabs.count() - 1, QColor(color))
        lay.addWidget(self.tabs, stretch=2)

        # Signal output display
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Current Signal:"))
        self.lbl_signal = QLabel("WAIT")
        self.lbl_signal.setObjectName("lbl_signal")
        self.lbl_signal.setAlignment(Qt.AlignCenter)
        self._set_signal_label("WAIT")
        out_row.addWidget(self.lbl_signal)
        out_row.addStretch()
        lay.addLayout(out_row)

        # Test panel
        test_grp = QGroupBox("Test on Synthetic Data")
        test_lay = QVBoxLayout(test_grp)
        test_btn_row = QHBoxLayout()
        self.btn_test = QPushButton("▶  Run Test")
        self.btn_test.clicked.connect(self._run_test)
        test_btn_row.addWidget(self.btn_test);
        test_btn_row.addStretch()
        test_lay.addLayout(test_btn_row)
        self.test_out = QTextEdit();
        self.test_out.setReadOnly(True);
        self.test_out.setMaximumHeight(160)
        self.test_out.setPlaceholderText("Click 'Run Test' to evaluate rules on synthetic OHLCV data...")
        test_lay.addWidget(self.test_out)
        lay.addWidget(test_grp)

        # Save / load
        bot = QHBoxLayout()
        self.btn_load = QPushButton("📂  Load Config")
        self.btn_save = QPushButton("💾  Save Config");
        self.btn_save.setObjectName("btn_save")
        self.btn_load.clicked.connect(self._load_config)
        self.btn_save.clicked.connect(self._save_config)
        bot.addWidget(self.btn_load);
        bot.addStretch();
        bot.addWidget(self.btn_save)
        lay.addLayout(bot)

    def _on_conflict_changed(self):
        self.engine.conflict_resolution = self.cb_conflict.currentData()

    def _on_changed(self):
        pass

    def _set_signal_label(self, signal_value: str):
        color = SIGNAL_COLORS.get(signal_value, MUTED)
        self.lbl_signal.setText(signal_value.replace("_", " "))
        self.lbl_signal.setStyleSheet(
            f"QLabel#lbl_signal {{ font-size:22px; font-weight:bold; padding:8px 18px; "
            f"border-radius:8px; background:{color}22; color:{color}; border:2px solid {color}; }}"
        )

    def _run_test(self):
        import numpy as np, pandas as pd
        try:
            np.random.seed(0);
            n = 100
            close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.5))
            df = pd.DataFrame({"open": close - 0.1, "high": close + 0.5, "low": close - 0.5,
                               "close": close, "volume": np.random.randint(1000, 5000, n).astype(float)})
            result = self.engine.evaluate(df)
            sig = result["signal_value"]
            self._set_signal_label(sig)
            lines = [f"🎯  Signal: {sig}  {'⚠️ CONFLICT' if result['conflict'] else ''}"]
            lines.append("")
            for s in SIGNAL_GROUPS:
                k = s.value
                rule_list = result["rule_results"].get(k, [])
                if not rule_list: continue
                fired = result["fired"].get(k, False)
                icon = "✅" if fired else "❌"
                lines.append(f"{icon} {SIGNAL_LABELS.get(k, k)}")
                for r in rule_list:
                    ri = "  ✔" if r["result"] else "  ✘"
                    lines.append(f"{ri}  {r['rule']}")
            self.test_out.setPlainText("\n".join(lines))
        except Exception as e:
            self.test_out.setPlainText(f"Error: {e}")

    def _save_config(self):
        ok = self.engine.save()
        if ok:
            QMessageBox.information(self, "Saved", f"Config saved to:\n{self.engine.config_file}")
            self.signals_updated.emit(self.engine.to_dict())
        else:
            QMessageBox.warning(self, "Error", "Save failed — check logs.")

    def _load_config(self):
        ok = self.engine.load()
        if ok:
            for sig, panel in self.panels.items():
                signal = OptionSignal(sig)
                panel.chk_enabled.setChecked(self.engine.is_enabled(signal))
                logic = self.engine.get_logic(signal)
                panel.rb_and.setChecked(logic == "AND");
                panel.rb_or.setChecked(logic == "OR")
                panel._refresh()
            QMessageBox.information(self, "Loaded", "Config reloaded from disk.")
        else:
            QMessageBox.warning(self, "Error", "Load failed or file not found.")

    def set_dataframe(self, df):
        self._test_df = df


# ── Standalone dialog wrapper ──────────────────────────────────────────────
class IndicatorRuleBuilderDialog(QDialog):
    signals_updated = pyqtSignal(dict)

    def __init__(self, engine: Optional[DynamicSignalEngine] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Option Signal Rule Builder")
        self.setMinimumSize(820, 700);
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self);
        lay.setContentsMargins(16, 16, 16, 16)
        self.builder = IndicatorRuleBuilderWidget(engine=engine, parent=self)
        self.builder.signals_updated.connect(self.signals_updated.emit)
        lay.addWidget(self.builder)
        close = QPushButton("Close");
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignRight)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dlg = IndicatorRuleBuilderDialog()
    dlg.show()
    sys.exit(app.exec_())
