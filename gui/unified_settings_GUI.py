# UnifiedSettingsGUI.py
# Full-page unified settings dialog — all saves routed through SettingsManager
# so settings are persisted, immediately applied to live TradeState, and
# broadcast via settings_changed signal to every connected component.
#
# Usage (preferred — with SettingsManager):
#   dlg = UnifiedSettingsGUI(parent, settings_manager=mgr)
#   dlg.exec_()
#
# Usage (legacy fallback — individual objects still accepted):
#   dlg = UnifiedSettingsGUI(
#       parent,
#       brokerage_setting=b, daily_setting=d, profit_stoploss_setting=p
#   )
#   dlg.exec_()

from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QListWidget, QListWidgetItem, QWidget, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QLabel, QPushButton,
    QScrollArea, QFrame, QGroupBox, QAbstractItemView, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QLocale, QObject
from PyQt5.QtGui import QFont, QDoubleValidator
import threading

from models.settings_manager import SettingsManager

try:
    from gui.BrokerageSetting import BrokerageSetting
except ImportError:
    from BrokerageSetting import BrokerageSetting

try:
    from gui.DailyTradeSetting import DailyTradeSetting
except ImportError:
    from DailyTradeSetting import DailyTradeSetting

try:
    from gui.ProfitStoplossSetting import ProfitStoplossSetting
except ImportError:
    from ProfitStoplossSetting import ProfitStoplossSetting

try:
    from BaseEnums import STOP, TRAILING
except ImportError:
    STOP = "STOP"
    TRAILING = "TRAILING"


# ─────────────────────────────────────────────────────────────────────────────
# Design tokens
# ─────────────────────────────────────────────────────────────────────────────

DARK     = "#0d1117"
SURFACE  = "#161b22"
ELEVATED = "#21262d"
BORDER   = "#30363d"
TEXT     = "#e6edf3"
MUTED    = "#8b949e"
DIM      = "#484f58"
ACCENT   = "#58a6ff"
SUCCESS  = "#3fb950"
DANGER   = "#f85149"
WARNING  = "#e3b341"
GREEN_BG = "#238636"

GLOBAL_STYLE = f"""
    QDialog, QWidget#page {{
        background: {DARK}; color: {TEXT};
    }}
    QLabel {{ color: {MUTED}; background: transparent; }}
    QLineEdit, QComboBox {{
        background: {ELEVATED}; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 5px;
        padding: 9px 12px; font-size: 10pt;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 2px solid {ACCENT}; }}
    QLineEdit:disabled {{ background: #13181f; color: {DIM}; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox QAbstractItemView {{
        background: {ELEVATED}; color: {TEXT};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT};
    }}
    QCheckBox {{ color: {TEXT}; spacing: 8px; font-size: 10pt; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; }}
    QCheckBox::indicator:unchecked {{ border: 2px solid {BORDER}; background: {ELEVATED}; }}
    QCheckBox::indicator:checked   {{ background: {GREEN_BG}; border: 2px solid #2ea043; }}
    QPushButton {{
        background: {GREEN_BG}; color: #fff; border: none;
        border-radius: 5px; padding: 10px 22px;
        font-weight: bold; font-size: 10pt;
    }}
    QPushButton:hover {{ background: #2ea043; }}
    QPushButton:pressed {{ background: #1a6e2b; }}
    QPushButton:disabled {{ background: {ELEVATED}; color: {DIM}; }}
    QPushButton#danger {{ background: #b91c1c; }}
    QPushButton#danger:hover {{ background: {DANGER}; }}
    QGroupBox {{
        color: {TEXT}; border: 1px solid {BORDER};
        border-radius: 7px; margin-top: 1.1em; padding-top: 16px;
        font-weight: bold; font-size: 10pt;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 8px; color: {TEXT}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: {SURFACE}; width: 8px; border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QFrame#separator {{ background: {BORDER}; max-height: 1px; }}
"""

NAV_STYLE = f"""
    QListWidget {{
        background: {SURFACE}; border: none;
        border-right: 1px solid {BORDER};
        outline: none; font-size: 11pt; color: {MUTED};
    }}
    QListWidget::item {{ padding: 14px 20px; }}
    QListWidget::item:selected {{
        background: {ELEVATED}; color: {TEXT};
        border-left: 3px solid {ACCENT};
    }}
    QListWidget::item:hover:!selected {{ background: #1c2128; color: {TEXT}; }}
"""

ERROR_FIELD_STYLE = (
    f"QLineEdit {{ background: #2d1a1a; border: 2px solid {DANGER}; "
    f"border-radius: 5px; padding: 9px 12px; color: {TEXT}; }}"
)


# ─────────────────────────────────────────────────────────────────────────────
# Tiny helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hint(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {DIM}; font-size: 8pt; background: transparent;")
    lbl.setWordWrap(True)
    return lbl

def _section_title(text):
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
    lbl.setStyleSheet(f"color: {TEXT}; background: transparent;")
    return lbl

def _separator():
    f = QFrame()
    f.setObjectName("separator")
    f.setFrameShape(QFrame.HLine)
    return f

def _scroll(inner):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QScrollArea.NoFrame)
    s.setWidget(inner)
    return s

def _save_row_layout(btn, cancel_fn=None):
    row = QHBoxLayout()
    row.setContentsMargins(0, 12, 0, 0)
    row.addStretch()
    if cancel_fn:
        c = QPushButton("Cancel")
        c.setObjectName("danger")
        c.setFixedHeight(40)
        c.clicked.connect(cancel_fn)
        row.addWidget(c)
    row.addWidget(btn)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Shared status strip
# ─────────────────────────────────────────────────────────────────────────────

class _StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        self._lbl = QLabel("")
        self._lbl.setAlignment(Qt.AlignVCenter)
        self._lbl.setStyleSheet(
            f"color: {SUCCESS}; font-size: 9pt; font-weight: bold; background: transparent;"
        )
        lay.addWidget(self._lbl)

        # Add a debug label to show when status is updated
        # logging.info("StatusBar initialized")

    def set_success(self, msg="✓  Settings saved & applied"):
        # logging.info(f"StatusBar success: {msg}")
        self._lbl.setStyleSheet(
            f"color: {SUCCESS}; font-size: 9pt; font-weight: bold; background: transparent;"
        )
        self._lbl.setText(msg)
        # Force immediate repaint
        self.repaint()
        QTimer.singleShot(5000, self.clear)

    def set_error(self, msg):
        # logging.info(f"StatusBar error: {msg}")
        self._lbl.setStyleSheet(
            f"color: {DANGER}; font-size: 9pt; font-weight: bold; background: transparent;"
        )
        self._lbl.setText(f"✗  {msg}")
        self.repaint()


# ─────────────────────────────────────────────────────────────────────────────
# Page 0 — Overview / General
# ─────────────────────────────────────────────────────────────────────────────

class _GeneralPage(QWidget):
    def __init__(self, mgr: SettingsManager, nav_fn, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._mgr = mgr
        self._nav = nav_fn
        self._build()
        # Auto-refresh overview whenever any section is saved
        mgr.settings_changed.connect(lambda _: self.refresh())

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(20)

        lay.addWidget(_section_title("⚡  Trading System — Settings Overview"))
        lay.addWidget(_separator())

        # Summary cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self._brokerage_card = self._make_card("🔑  Brokerage",   1)
        self._daily_card     = self._make_card("📊  Daily Trade",  2)
        self._profit_card    = self._make_card("💹  Profit & SL",  3)
        cards_row.addWidget(self._brokerage_card)
        cards_row.addWidget(self._daily_card)
        cards_row.addWidget(self._profit_card)
        lay.addLayout(cards_row)

        lay.addWidget(_separator())

        attn_lbl = QLabel("⚠️  Requires Attention")
        attn_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        attn_lbl.setStyleSheet(f"color: {WARNING}; background: transparent;")
        lay.addWidget(attn_lbl)

        self._attn_container = QVBoxLayout()
        self._attn_container.setSpacing(8)
        lay.addLayout(self._attn_container)

        lay.addWidget(_separator())

        snap_lbl = QLabel("📋  Current Configuration Snapshot")
        snap_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        snap_lbl.setStyleSheet(f"color: {TEXT}; background: transparent;")
        lay.addWidget(snap_lbl)

        self._snap_container = QVBoxLayout()
        self._snap_container.setSpacing(4)
        lay.addLayout(self._snap_container)
        lay.addStretch()

        outer.addWidget(_scroll(inner))
        self.refresh()

    def _make_card(self, label, nav_idx):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{ background: {ELEVATED}; border: 1px solid {BORDER}; border-radius: 8px; }}
            QFrame:hover {{ border: 1px solid {ACCENT}; }}
        """)
        card.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)

        title = QLabel(label)
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT}; background: transparent;")

        status = QLabel("…")
        status.setObjectName("status")
        status.setStyleSheet(f"color: {MUTED}; font-size: 9pt; background: transparent;")

        goto = QPushButton("Configure →")
        goto.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {ACCENT};
                border: 1px solid {ACCENT}; border-radius: 4px;
                padding: 5px 12px; font-size: 9pt;
            }}
            QPushButton:hover {{ background: #1a2a3a; }}
        """)
        goto.clicked.connect(lambda _, i=nav_idx: self._nav(i))

        lay.addWidget(title)
        lay.addWidget(status)
        lay.addWidget(goto)
        return card

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self):
        self._clear(self._attn_container)
        self._clear(self._snap_container)

        issues = self._gather_issues()
        b_ok = not any(s == "brokerage" for _, s in issues)
        d_ok = not any(s == "daily"     for _, s in issues)
        p_ok = not any(s == "profit"    for _, s in issues)

        for card, ok in [
            (self._brokerage_card, b_ok),
            (self._daily_card,     d_ok),
            (self._profit_card,    p_ok),
        ]:
            st = card.findChild(QLabel, "status")
            if st:
                if ok:
                    st.setText("✓  All fields configured")
                    st.setStyleSheet(f"color: {SUCCESS}; font-size: 9pt; background: transparent;")
                else:
                    st.setText("⚠  Missing required fields")
                    st.setStyleSheet(f"color: {WARNING}; font-size: 9pt; background: transparent;")

        if not issues:
            ok_lbl = QLabel("✓  All settings are configured and ready.")
            ok_lbl.setStyleSheet(
                f"color: {SUCCESS}; font-size: 10pt; font-weight: bold; background: transparent;"
            )
            self._attn_container.addWidget(ok_lbl)
        else:
            fix_map = {"brokerage": 1, "daily": 2, "profit": 3}
            for msg, section in issues:
                row = QFrame()
                row.setStyleSheet(
                    "QFrame { background: #2d1a1a; border: 1px solid #7a1e1e; border-radius: 5px; }"
                )
                rlay = QHBoxLayout(row)
                rlay.setContentsMargins(14, 10, 14, 10)
                rlay.setSpacing(14)

                txt = QLabel(f"• {msg}")
                txt.setStyleSheet(f"color: {DANGER}; background: transparent;")
                txt.setWordWrap(True)

                fix = QPushButton("Fix →")
                fix.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; color: {DANGER};
                        border: 1px solid {DANGER}; border-radius: 4px;
                        padding: 4px 10px; font-size: 9pt;
                    }}
                    QPushButton:hover {{ background: #3a1212; }}
                """)
                fix.setFixedWidth(60)
                fix.clicked.connect(lambda _, s=section: self._nav(fix_map.get(s, 0)))

                rlay.addWidget(txt, 1)
                rlay.addWidget(fix)
                self._attn_container.addWidget(row)

        # Snapshot
        snap = self._mgr.snapshot()
        rows = [
            ("Exchange",         snap["exchange"]          or "—"),
            ("Derivative",       snap["derivative"]        or "—"),
            ("Lot Size",         str(snap["lot_size"])),
            ("Week",             str(snap["week"])),
            ("History Interval", snap["history_interval"]  or "—"),
            ("Profit Type",      snap["profit_type"]       or "—"),
            ("Take Profit",      f"{snap['tp_percentage']}%"),
            ("Stoploss",         f"{snap['stoploss_percentage']}%"),
            ("Capital Reserve",  f"₹{snap['capital_reserve']:,}"),
            ("Sideway Trade",    "Enabled" if snap["sideway_zone_trade"] else "Disabled"),
            ("Client ID",        (snap["client_id"][:12] + "…")
                                 if len(snap["client_id"]) > 12
                                 else (snap["client_id"] or "—")),
            ("Redirect URI",     snap["redirect_uri"]      or "—"),
        ]
        for label, value in rows:
            rw = QWidget()
            rw.setObjectName("page")
            rl = QHBoxLayout(rw)
            rl.setContentsMargins(0, 2, 0, 2)
            k = QLabel(label)
            k.setStyleSheet(
                f"color: {MUTED}; font-size: 9pt; min-width: 160px; background: transparent;"
            )
            v = QLabel(value)
            v.setStyleSheet(
                f"color: {TEXT}; font-size: 9pt; font-weight: 500; background: transparent;"
            )
            rl.addWidget(k)
            rl.addWidget(v)
            rl.addStretch()
            self._snap_container.addWidget(rw)

    def _gather_issues(self):
        b, d, p = self._mgr.brokerage, self._mgr.daily, self._mgr.profit
        issues = []
        if not b.client_id:          issues.append(("Brokerage: Client ID is not set",        "brokerage"))
        if not b.secret_key:         issues.append(("Brokerage: Secret Key is not set",       "brokerage"))
        if not b.redirect_uri:       issues.append(("Brokerage: Redirect URI is not set",     "brokerage"))
        if not d.exchange:           issues.append(("Daily Trade: Exchange is not set",        "daily"))
        if not d.derivative:         issues.append(("Daily Trade: Derivative symbol not set", "daily"))
        if d.lot_size < 1:           issues.append(("Daily Trade: Lot Size must be ≥ 1",      "daily"))
        if p.tp_percentage <= 0:     issues.append(("Profit/SL: Take Profit % must be > 0",   "profit"))
        if p.stoploss_percentage <= 0: issues.append(("Profit/SL: Stoploss % must be > 0",   "profit"))
        return issues


# ─────────────────────────────────────────────────────────────────────────────
# Page 1 — Brokerage Settings
# ─────────────────────────────────────────────────────────────────────────────

class _BrokeragePage(QWidget):
    def __init__(self, mgr: SettingsManager, status_bar: _StatusBar, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._mgr    = mgr
        self._status = status_bar
        self._build()
        mgr.settings_changed.connect(self._on_external_change)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(16)

        lay.addWidget(_section_title("🔑  Brokerage API Settings"))
        lay.addWidget(_separator())

        grp = QGroupBox("API Credentials")
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        b = self._mgr.brokerage

        self.client_id_edit = QLineEdit(b.client_id)
        self.client_id_edit.setPlaceholderText("e.g. ABCD1234-5678-EFGH")
        form.addRow("🆔  Client ID:", self.client_id_edit)
        form.addRow("", _hint("Unique identifier for your registered brokerage app."))

        self.secret_key_edit = QLineEdit(b.secret_key)
        self.secret_key_edit.setPlaceholderText("Paste your secret key here")
        self.secret_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("🔑  Secret Key:", self.secret_key_edit)
        form.addRow("", _hint("Private key — stored locally at config/brokerage_setting.json."))

        self.redirect_edit = QLineEdit(b.redirect_uri)
        self.redirect_edit.setPlaceholderText("e.g. https://127.0.0.1:8182")
        form.addRow("🔗  Redirect URI:", self.redirect_edit)
        form.addRow("", _hint("Must exactly match the URI registered in your brokerage developer portal."))

        lay.addWidget(grp)

        for title, body in [
            ("🆔  Client ID",
             "A unique public identifier assigned when you register your app. Not secret."),
            ("🔑  Secret Key",
             "Paired with Client ID to prove your app's identity. Treat it like a password. "
             "Regenerate immediately if compromised."),
            ("🔗  Redirect URI",
             "Must match character-for-character what is in your portal. "
             "Mismatches are the #1 cause of OAuth failures."),
        ]:
            c = QFrame()
            c.setStyleSheet(
                f"QFrame {{ background: {ELEVATED}; border: 1px solid {BORDER}; border-radius: 6px; }}"
            )
            cl = QVBoxLayout(c)
            cl.setContentsMargins(14, 12, 14, 12)
            t = QLabel(title)
            t.setFont(QFont("Segoe UI", 10, QFont.Bold))
            t.setStyleSheet(f"color: {TEXT}; background: transparent;")
            bl = QLabel(body)
            bl.setWordWrap(True)
            bl.setStyleSheet(f"color: {MUTED}; font-size: 9pt; background: transparent;")
            cl.addWidget(t)
            cl.addWidget(bl)
            lay.addWidget(c)

        self._save_btn = QPushButton("💾  Save Changes")
        self._save_btn.setFixedHeight(40)
        self._save_btn.clicked.connect(self._save)
        lay.addLayout(_save_row_layout(self._save_btn))
        lay.addStretch()
        outer.addWidget(_scroll(inner))

    def _on_external_change(self, section: str):
        if section in ("brokerage", "all"):
            b = self._mgr.brokerage
            self.client_id_edit.setText(b.client_id)
            self.secret_key_edit.setText(b.secret_key)
            self.redirect_edit.setText(b.redirect_uri)

    def _save(self):
        print(f"Starting save for section")
        cid = self.client_id_edit.text().strip()
        sk = self.secret_key_edit.text().strip()
        ruri = self.redirect_edit.text().strip()

        print(f"Values - Client ID: {cid[:5]}..., Secret Key: {'*' * len(sk)}, Redirect: {ruri}")

        if not all([cid, sk, ruri]):
            self._status.set_error("All brokerage fields are required")
            return

        b = self._mgr.brokerage
        b.client_id = cid
        b.secret_key = sk
        b.redirect_uri = ruri

        self._save_btn.setEnabled(False)
        self._save_btn.setText("⏳  Saving…")

        def _do():
            try:
                ok, err = self._mgr.save_section("brokerage")
                print(f"Save result: ok={ok}, err={err}")
                QTimer.singleShot(0, lambda: self._on_done(ok, err))
            except Exception as e:
                print(f"Exception in save thread: {e}")
                QTimer.singleShot(0, lambda: self._on_done(False, str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _on_done(self, ok, err):
        self._save_btn.setEnabled(True)
        self._save_btn.setText("💾  Save Changes")
        if ok:
            self._status.set_success("✓  Settings saved & applied")
            # Force a visible update
            QTimer.singleShot(100, lambda: self._status.set_success("✓  Settings saved & applied"))
        else:
            self._status.set_error(f"Save failed: {err}")
            # Show a popup for critical errors
            QMessageBox.warning(self, "Save Error", f"Failed to save settings:\n{err}")

# ─────────────────────────────────────────────────────────────────────────────
# Page 2 — Daily Trade Settings
# ─────────────────────────────────────────────────────────────────────────────

class _DailyTradePage(QWidget):
    INTERVAL_CHOICES = [
        ("5 seconds",    "5S"),  ("10 seconds",  "10S"), ("15 seconds",  "15S"),
        ("30 seconds",   "30S"), ("45 seconds",  "45S"), ("1 minute",    "1m"),
        ("2 minutes",    "2m"),  ("3 minutes",   "3m"),  ("5 minutes",   "5m"),
        ("10 minutes",   "10m"), ("15 minutes",  "15m"), ("20 minutes",  "20m"),
        ("30 minutes",   "30m"), ("60 minutes",  "60m"), ("120 minutes", "120m"),
        ("240 minutes",  "240m"),
    ]
    VALIDATION = {
        "week":              (0,   53),
        "lot_size":          (1,   10000),
        "call_lookback":     (0,   100),
        "put_lookback":      (0,   100),
        "max_num_of_option": (1,   10000),
        "lower_percentage":  (0.0, 100.0),
        "cancel_after":      (1,   60),
        "capital_reserve":   (0,   1_000_000),
    }

    def __init__(self, mgr: SettingsManager, status_bar: _StatusBar, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._mgr    = mgr
        self._status = status_bar
        self._entries = {}   # key → (QLineEdit, type)
        self._build()
        mgr.settings_changed.connect(self._on_external_change)

    @staticmethod
    def _form_defaults(form):
        form.setSpacing(8)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

    def _field(self, form, label, key, typ, value, placeholder, hint_text):
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        form.addRow(f"{label}:", edit)
        form.addRow("", _hint(hint_text))
        self._entries[key] = (edit, typ)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(16)

        lay.addWidget(_section_title("📊  Daily Trade Settings"))
        lay.addWidget(_separator())

        d = self._mgr.daily

        # ── Group 1: Market ──────────────────────────────────────────────────
        g1 = QGroupBox("Market Configuration")
        f1 = QFormLayout(g1)
        self._form_defaults(f1)
        self._field(f1, "🌐  Exchange",   "exchange",   str,   d.exchange,
                    "e.g. NSE",    "Stock exchange to trade on (NSE, BSE, NFO…)")
        self._field(f1, "💡  Derivative", "derivative", str,   d.derivative,
                    "e.g. NIFTY50","Underlying symbol, e.g. NIFTY, BANKNIFTY")
        self._field(f1, "🔢  Lot Size",   "lot_size",   int,   str(d.lot_size),
                    "e.g. 75",     "Standard lot size for the selected derivative (1–10 000)")
        self._field(f1, "📆  Week",       "week",       int,   str(d.week),
                    "0 = current", "0 = nearest expiry; higher = far-dated contracts (0–53)")
        lay.addWidget(g1)

        # ── Group 2: Signal ──────────────────────────────────────────────────
        g2 = QGroupBox("Signal & Lookback")
        f2 = QFormLayout(g2)
        self._form_defaults(f2)
        self._field(f2, "🔎  Call Lookback",        "call_lookback",     int,
                    str(d.call_lookback),    "e.g. 5",
                    "Historical candles for call entry signal (0–100)")
        self._field(f2, "🔎  Put Lookback",         "put_lookback",      int,
                    str(d.put_lookback),     "e.g. 5",
                    "Historical candles for put entry signal (0–100)")
        self._field(f2, "📈  Max Option Positions", "max_num_of_option", int,
                    str(d.max_num_of_option),"e.g. 10",
                    "Max concurrent open option positions (1–10 000)")
        self._field(f2, "📉  Lower Percentage (%)", "lower_percentage",  float,
                    str(d.lower_percentage), "e.g. 2.0",
                    "Min % threshold for signal filtering (0–100)")
        lay.addWidget(g2)

        # ── Group 3: Execution ───────────────────────────────────────────────
        g3 = QGroupBox("Execution & Capital")
        f3 = QFormLayout(g3)
        self._form_defaults(f3)
        self._field(f3, "⏱️  Cancel After (s)",    "cancel_after",    int,
                    str(d.cancel_after),    "e.g. 5",
                    "Seconds before unfilled limit order is auto-cancelled (1–60)")
        self._field(f3, "💰  Capital Reserve (₹)", "capital_reserve", int,
                    str(d.capital_reserve), "e.g. 50000",
                    "Amount kept aside and never deployed (0–1 000 000)")

        self.interval_combo = QComboBox()
        for label, val in self.INTERVAL_CHOICES:
            self.interval_combo.addItem(label, val)
        cur = d.history_interval
        for i, (_, v) in enumerate(self.INTERVAL_CHOICES):
            if v == cur:
                self.interval_combo.setCurrentIndex(i)
                break
        f3.addRow("⏱️  History Interval:", self.interval_combo)
        f3.addRow("", _hint("Candle timeframe for historical price data used in signal generation."))

        self.sideway_check = QCheckBox("Enable trading during sideway zone (12:00–14:00)")
        self.sideway_check.setChecked(d.sideway_zone_trade)
        f3.addRow("↔️  Sideway Zone:", self.sideway_check)
        f3.addRow("", _hint("When disabled, bot pauses entries during the low-volatility midday window."))
        lay.addWidget(g3)

        self._save_btn = QPushButton("💾  Save Changes")
        self._save_btn.setFixedHeight(40)
        self._save_btn.clicked.connect(self._save)
        lay.addLayout(_save_row_layout(self._save_btn))
        lay.addStretch()
        outer.addWidget(_scroll(inner))

    def _on_external_change(self, section: str):
        """Reload fields when saved from outside (e.g. save_all)."""
        if section not in ("daily", "all"):
            return
        d = self._mgr.daily
        reload_map = {
            "exchange":          str(d.exchange),
            "derivative":        str(d.derivative),
            "lot_size":          str(d.lot_size),
            "week":              str(d.week),
            "call_lookback":     str(d.call_lookback),
            "put_lookback":      str(d.put_lookback),
            "max_num_of_option": str(d.max_num_of_option),
            "lower_percentage":  str(d.lower_percentage),
            "cancel_after":      str(d.cancel_after),
            "capital_reserve":   str(d.capital_reserve),
        }
        for key, val in reload_map.items():
            if key in self._entries:
                self._entries[key][0].setText(val)
        cur = d.history_interval
        for i, (_, v) in enumerate(self.INTERVAL_CHOICES):
            if v == cur:
                self.interval_combo.setCurrentIndex(i)
                break
        self.sideway_check.setChecked(d.sideway_zone_trade)

    def _validate(self):
        errors, data = [], {}
        for key, (edit, typ) in self._entries.items():
            val_str = edit.text().strip()
            if not val_str:
                data[key] = 0 if typ in (int, float) else ""
                continue
            if typ == str:
                data[key] = val_str
                edit.setStyleSheet("")
                continue
            try:
                val = int(float(val_str)) if typ == int else float(val_str)
                if key in self.VALIDATION:
                    lo, hi = self.VALIDATION[key]
                    if not (lo <= val <= hi):
                        errors.append(f"{key} must be between {lo} and {hi}")
                        edit.setStyleSheet(ERROR_FIELD_STYLE)
                        continue
                data[key] = val
                edit.setStyleSheet("")
            except ValueError:
                errors.append(f"Invalid number for {key}")
                edit.setStyleSheet(ERROR_FIELD_STYLE)
        return errors, data

    def _save(self):
        errors, data = self._validate()
        if errors:
            self._status.set_error(errors[0])
            return

        data["history_interval"]   = self.interval_combo.currentData()
        data["sideway_zone_trade"]  = self.sideway_check.isChecked()

        # Write validated values into the shared setting object
        d = self._mgr.daily
        for k, v in data.items():
            setattr(d, k, v)

        self._save_btn.setEnabled(False)
        self._save_btn.setText("⏳  Saving…")

        def _do():
            # persist → apply to TradeState → emit settings_changed
            ok, err = self._mgr.save_section("daily")
            QTimer.singleShot(0, lambda: self._on_done(ok, err))

        threading.Thread(target=_do, daemon=True).start()

    def _on_done(self, ok, err):
        self._save_btn.setEnabled(True)
        self._save_btn.setText("💾  Save Changes")
        if ok:
            self._status.set_success("✓  Daily trade settings saved & applied to live engine")
        else:
            self._status.set_error(f"Save failed: {err}")


# ─────────────────────────────────────────────────────────────────────────────
# Page 3 — Profit & Stoploss Settings
# ─────────────────────────────────────────────────────────────────────────────

class _ProfitPage(QWidget):
    VALIDATION = {
        "tp_percentage":         (0.1, 100.0),
        "stoploss_percentage":   (0.1,  50.0),
        "trailing_first_profit": (0.1,  50.0),
        "max_profit":            (0.1, 200.0),
        "profit_step":           (0.1,  20.0),
        "loss_step":             (0.1,  20.0),
    }

    def __init__(self, mgr: SettingsManager, status_bar: _StatusBar, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._mgr    = mgr
        self._status = status_bar
        self._entries = {}   # key → QLineEdit
        self._build()
        mgr.settings_changed.connect(self._on_external_change)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(16)

        lay.addWidget(_section_title("💹  Profit & Stoploss Settings"))
        lay.addWidget(_separator())

        validator = QDoubleValidator()
        validator.setLocale(QLocale.c())
        p = self._mgr.profit

        # ── Group 1: Profit Mode ─────────────────────────────────────────────
        g1 = QGroupBox("Profit Mode")
        f1 = QFormLayout(g1)
        f1.setSpacing(8); f1.setVerticalSpacing(4)
        f1.setLabelAlignment(Qt.AlignRight)
        f1.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.profit_type_combo = QComboBox()
        self.profit_type_combo.addItem("STOP — Fixed take-profit target", STOP)
        self.profit_type_combo.addItem("TRAILING — Dynamic lock-in",      TRAILING)
        self.profit_type_combo.setCurrentIndex(0 if p.profit_type == STOP else 1)
        self.profit_type_combo.currentIndexChanged.connect(self._on_type_change)
        f1.addRow("💰  Profit Type:", self.profit_type_combo)
        f1.addRow("", _hint("STOP exits at a fixed target. TRAILING locks in gains as price moves in your favour."))
        lay.addWidget(g1)

        # ── Group 2: Core thresholds ─────────────────────────────────────────
        g2 = QGroupBox("Core Thresholds")
        f2 = QFormLayout(g2)
        f2.setSpacing(8); f2.setVerticalSpacing(4)
        f2.setLabelAlignment(Qt.AlignRight)
        f2.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._pfield(f2, validator, "💰  Take Profit (%)", "tp_percentage",
                     p.tp_percentage,       "e.g. 15.0", "Exit at this % gain from entry value (0.1–100)")
        self._pfield(f2, validator, "🛑  Stoploss (%)",    "stoploss_percentage",
                     p.stoploss_percentage, "e.g. 7.0",  "Exit at this % loss from entry value (0.1–50)")
        lay.addWidget(g2)

        # ── Group 3: Trailing params ─────────────────────────────────────────
        self._trailing_group = QGroupBox("Trailing Parameters  (TRAILING mode only)")
        f3 = QFormLayout(self._trailing_group)
        f3.setSpacing(8); f3.setVerticalSpacing(4)
        f3.setLabelAlignment(Qt.AlignRight)
        f3.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._pfield(f3, validator, "🚀  Trailing First Profit (%)", "trailing_first_profit",
                     p.trailing_first_profit, "e.g. 3.0",  "Min profit % before trailing stop activates (0.1–50)")
        self._pfield(f3, validator, "📈  Max Profit (%)",            "max_profit",
                     p.max_profit,            "e.g. 30.0", "Stop target ceiling for trailing (0.1–200)")
        self._pfield(f3, validator, "⬆️  Profit Step (%)",           "profit_step",
                     p.profit_step,           "e.g. 2.0",  "Step size to advance trailing stop (0.1–20)")
        self._pfield(f3, validator, "⬇️  Loss Step (%)",             "loss_step",
                     p.loss_step,             "e.g. 2.0",  "Max pullback from peak before stop fires (0.1–20)")
        lay.addWidget(self._trailing_group)

        self._save_btn = QPushButton("💾  Save Changes")
        self._save_btn.setFixedHeight(40)
        self._save_btn.clicked.connect(self._save)
        lay.addLayout(_save_row_layout(self._save_btn))
        lay.addStretch()
        outer.addWidget(_scroll(inner))
        self._on_type_change()

    def _pfield(self, form, validator, label, key, value, placeholder, hint_text):
        edit = QLineEdit(str(value))
        edit.setPlaceholderText(placeholder)
        edit.setValidator(validator)
        form.addRow(f"{label}:", edit)
        form.addRow("", _hint(hint_text))
        self._entries[key] = edit

    def _on_type_change(self):
        trailing_keys = {"trailing_first_profit", "max_profit", "profit_step", "loss_step"}
        is_trailing = self.profit_type_combo.currentData() == TRAILING
        for key, edit in self._entries.items():
            if key in trailing_keys:
                edit.setEnabled(is_trailing)
        self._trailing_group.setEnabled(is_trailing)

    def _on_external_change(self, section: str):
        if section not in ("profit", "all"):
            return
        p = self._mgr.profit
        for key, edit in self._entries.items():
            edit.setText(str(getattr(p, key)))
        self.profit_type_combo.setCurrentIndex(0 if p.profit_type == STOP else 1)

    def _validate(self):
        errors, data = [], {}
        profit_type = self.profit_type_combo.currentData()
        required = ["tp_percentage", "stoploss_percentage"]
        if profit_type == TRAILING:
            required += ["trailing_first_profit", "max_profit", "profit_step", "loss_step"]

        for key in required:
            edit = self._entries[key]
            val_str = edit.text().strip()
            if not val_str:
                errors.append(f"{key.replace('_', ' ').title()} is required")
                edit.setStyleSheet(ERROR_FIELD_STYLE)
                continue
            try:
                val = float(val_str)
                lo, hi = self.VALIDATION[key]
                if not (lo <= val <= hi):
                    errors.append(f"{key} must be between {lo} and {hi}")
                    edit.setStyleSheet(ERROR_FIELD_STYLE)
                    continue
                data[key] = val
                edit.setStyleSheet("")
            except ValueError:
                errors.append(f"Invalid number for {key}")
                edit.setStyleSheet(ERROR_FIELD_STYLE)

        if "max_profit" in data and "trailing_first_profit" in data:
            if data["max_profit"] <= data["trailing_first_profit"]:
                errors.append("Max Profit must be greater than Trailing First Profit")

        data["profit_type"] = profit_type
        return errors, data

    def _save(self):
        errors, data = self._validate()
        if errors:
            self._status.set_error(errors[0])
            return

        p = self._mgr.profit
        for k, v in data.items():
            setattr(p, k, v)

        self._save_btn.setEnabled(False)
        self._save_btn.setText("⏳  Saving…")

        def _do():
            ok, err = self._mgr.save_section("profit")
            QTimer.singleShot(0, lambda: self._on_done(ok, err))

        threading.Thread(target=_do, daemon=True).start()

    def _on_done(self, ok, err):
        self._save_btn.setEnabled(True)
        self._save_btn.setText("💾  Save Changes")
        if ok:
            self._status.set_success("✓  Profit & stoploss settings saved & applied to live engine")
        else:
            self._status.set_error(f"Save failed: {err}")


# ─────────────────────────────────────────────────────────────────────────────
# Main Unified Settings Dialog
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedSettingsGUI(QDialog):
    """
    Full-page unified settings dialog with sidebar navigation.

    All saves are routed through SettingsManager which:
      1. Persists to JSON atomically
      2. Calls apply_to_state() to push values into the live TradeState
      3. Emits settings_changed(section) so every connected widget refreshes

    Preferred usage (wire up SettingsManager once in TradingGUI):
        mgr = SettingsManager()
        mgr.register_state(trading_app.state)
        dlg = UnifiedSettingsGUI(parent, settings_manager=mgr)
        dlg.exec_()

    Legacy fallback (individual objects still accepted):
        dlg = UnifiedSettingsGUI(
            parent,
            brokerage_setting=b, daily_setting=d,
            profit_stoploss_setting=p, app=trading_app
        )
        dlg.exec_()
    """

    NAV_ITEMS = [
        ("🏠  Overview",          "All settings at a glance"),
        ("🔑  Brokerage",         "API credentials & OAuth"),
        ("📊  Daily Trade",        "Market, signal & execution"),
        ("💹  Profit & Stoploss",  "TP, SL & trailing config"),
    ]

    def __init__(self, parent=None, *,
                 settings_manager: SettingsManager = None,
                 # legacy kwargs
                 brokerage_setting=None,
                 daily_setting=None,
                 profit_stoploss_setting=None,
                 app=None):
        super().__init__(parent)

        if settings_manager is not None:
            self._mgr = settings_manager
        else:
            # Wrap individual objects inside a SettingsManager so the rest
            # of the code path is identical.
            self._mgr = _make_legacy_manager(
                brokerage_setting, daily_setting, profit_stoploss_setting, app
            )

        self.setWindowTitle("⚙️  Algo Trading — Settings")
        self.setMinimumSize(1100, 720)
        self.resize(1200, 800)
        self.setModal(True)
        self.setStyleSheet(GLOBAL_STYLE)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title bar ────────────────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(24, 0, 24, 0)

        app_title = QLabel("⚙️  Trading System Settings")
        app_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        app_title.setStyleSheet(f"color: {TEXT}; background: transparent;")

        close_btn = QPushButton("✕  Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {MUTED};
                border: 1px solid {BORDER}; border-radius: 4px;
                padding: 5px 14px; font-size: 9pt;
            }}
            QPushButton:hover {{ color: {TEXT}; border-color: {MUTED}; }}
        """)
        close_btn.clicked.connect(self.accept)

        tb_lay.addWidget(app_title)
        tb_lay.addStretch()
        tb_lay.addWidget(close_btn)
        root.addWidget(title_bar)

        # ── Body: sidebar + stacked pages ────────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {DARK};")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # Sidebar
        self._nav = QListWidget()
        self._nav.setFixedWidth(210)
        self._nav.setStyleSheet(NAV_STYLE)
        self._nav.setSelectionMode(QAbstractItemView.SingleSelection)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for label, tooltip in self.NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setToolTip(tooltip)
            item.setSizeHint(item.sizeHint().__class__(210, 52))
            self._nav.addItem(item)
        self._nav.currentRowChanged.connect(self._switch_page)
        body_lay.addWidget(self._nav)

        # Pages
        self._status_bar   = _StatusBar()
        self._stack        = QStackedWidget()
        self._stack.setStyleSheet(f"background: {DARK};")

        self._general_page   = _GeneralPage(self._mgr, nav_fn=self._switch_to)
        self._brokerage_page = _BrokeragePage(self._mgr, self._status_bar)
        self._daily_page     = _DailyTradePage(self._mgr, self._status_bar)
        self._profit_page    = _ProfitPage(self._mgr, self._status_bar)

        self._stack.addWidget(self._general_page)
        self._stack.addWidget(self._brokerage_page)
        self._stack.addWidget(self._daily_page)
        self._stack.addWidget(self._profit_page)

        body_lay.addWidget(self._stack, 1)
        root.addWidget(body, 1)
        root.addWidget(self._status_bar)

        self._nav.setCurrentRow(0)

    def _switch_to(self, index: int):
        self._nav.setCurrentRow(index)

    def _switch_page(self, index: int):
        self._stack.setCurrentIndex(index)
        if index == 0:
            self._general_page.refresh()


def _make_legacy_manager(brokerage=None, daily=None, profit=None, app=None) -> SettingsManager:
    """
    Construct a SettingsManager that wraps already-loaded setting objects.
    """
    import threading as _threading
    import logging

    try:
        # Create manager normally
        mgr = SettingsManager()
    except Exception as e:
        logging.error(f"Failed to create SettingsManager: {e}")
        # Fallback: create with explicit paths
        mgr = SettingsManager(
            brokerage_json="config/brokerage_setting.json",
            daily_json="config/daily_trade_setting.json",
            profit_json="config/profit_stoploss_setting.json"
        )

    # Replace the auto-loaded instances with the provided ones
    if brokerage:
        mgr.brokerage = brokerage
    if daily:
        mgr.daily = daily
    if profit:
        mgr.profit = profit

    if app is not None:
        state = getattr(app, "state", None)
        if state is not None:
            try:
                mgr.register_state(state)
            except Exception as e:
                logging.error(f"Failed to register state: {e}")

    return mgr