"""
license/activation_dialog.py
=============================
PyQt5 dialogs for activation and trial management.

Classes
───────
  ActivationDialog     — Two-tab modal shown on first run, expiry, or revocation
                           Tab 1 "Free Trial"  — email only, one-click 7-day trial
                           Tab 2 "Activate"    — order_id + email, paid license
  TrialExpiryBanner    — Amber in-app banner counting down trial days remaining
  UpdateBanner         — Blue dismissible banner for optional app updates
  MandatoryUpdateDialog — Blocking dialog when a forced update is required
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QProgressBar, QTabWidget, QWidget,
)

from license.license_manager import (
    LicenseManager, LicenseResult, license_manager, PLAN_TRIAL, TRIAL_DURATION_DAYS,
)

logger = logging.getLogger(__name__)

# ── Shared colour palette ──────────────────────────────────────────────────────
_BG = "#0d1117"
_SURFACE = "#161b22"
_BORDER = "#30363d"
_ACCENT = "#238636"  # green  — paid
_ACCENT_H = "#2ea043"
_TRIAL = "#1f6feb"  # blue   — trial (visually distinct from paid)
_TRIAL_H = "#388bfd"
_TEXT = "#e6edf3"
_SUBTEXT = "#8b949e"
_ERROR = "#f85149"
_WARN = "#d29922"
_WARN_BG = "#272115"


# ── Worker threads ─────────────────────────────────────────────────────────────

class _TrialWorker(QThread):
    result_ready = pyqtSignal(object)  # LicenseResult

    def __init__(self, email: str, manager: LicenseManager):
        super().__init__()
        self._email = email
        self._manager = manager

    def run(self):
        self.result_ready.emit(self._manager.start_trial(self._email))


class _ActivationWorker(QThread):
    result_ready = pyqtSignal(object)  # LicenseResult

    def __init__(self, order_id: str, email: str, manager: LicenseManager):
        super().__init__()
        self._order_id = order_id
        self._email = email
        self._manager = manager

    def run(self):
        self.result_ready.emit(self._manager.activate(self._order_id, self._email))


# ── Shared stylesheet ──────────────────────────────────────────────────────────

_DIALOG_CSS = f"""
    QDialog {{
        background: {_BG};
    }}
    QLabel {{
        color: {_TEXT};
        background: transparent;
    }}
    QTabWidget::pane {{
        border: 1px solid {_BORDER};
        border-radius: 0 6px 6px 6px;
        background: {_SURFACE};
    }}
    QTabBar::tab {{
        background: {_BG};
        color: {_SUBTEXT};
        padding: 10px 0;
        border: 1px solid {_BORDER};
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-size: 13px;
        font-weight: bold;
        min-width: 170px;
    }}
    QTabBar::tab:selected {{
        background: {_SURFACE};
        color: {_TEXT};
    }}
    QLineEdit {{
        background: {_BG};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border: 1px solid {_TRIAL};
    }}
    QPushButton#trialBtn {{
        background: {_TRIAL};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 12px 24px;
        font-size: 14px;
        font-weight: bold;
    }}
    QPushButton#trialBtn:hover    {{ background: {_TRIAL_H}; }}
    QPushButton#trialBtn:disabled {{ background: #21262d; color: {_SUBTEXT}; }}
    QPushButton#activateBtn {{
        background: {_ACCENT};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 12px 24px;
        font-size: 14px;
        font-weight: bold;
    }}
    QPushButton#activateBtn:hover    {{ background: {_ACCENT_H}; }}
    QPushButton#activateBtn:disabled {{ background: #21262d; color: {_SUBTEXT}; }}
    QProgressBar {{
        background: {_SURFACE};
        border: 1px solid {_BORDER};
        border-radius: 4px;
        height: 5px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        border-radius: 4px;
    }}
"""


# ── ActivationDialog ───────────────────────────────────────────────────────────

class ActivationDialog(QDialog):
    """
    Two-tab gate dialog shown whenever a valid license is required.

    Parameters
    ──────────
    reason        — Human-readable failure reason shown in a banner ('' = first run).
    prefill_email — Pre-populates email fields (e.g. after trial expiry).
    start_on_tab  — "trial" (default) or "activate".
    """

    activation_success = pyqtSignal(object)  # LicenseResult

    def __init__(
            self,
            parent=None,
            reason: str = "",
            manager: LicenseManager = None,
            prefill_email: str = "",
            start_on_tab: str = "trial",
    ):
        super().__init__(parent)
        self._reason = reason
        self._manager = manager or license_manager
        self._prefill_email = prefill_email
        self._start_on_tab = start_on_tab
        self._worker: Optional[QThread] = None

        self.setWindowTitle("Algo Trading Pro")
        self.setModal(True)
        self.setFixedWidth(500)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(_DIALOG_CSS)
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        # Header
        title = QLabel("🚀  Algo Trading Pro")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        root.addSpacing(4)
        tagline = QLabel("Professional algorithmic trading — start free, upgrade anytime")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(f"color: {_SUBTEXT}; font-size: 12px;")
        root.addWidget(tagline)
        root.addSpacing(18)

        # Reason banner — shown for expiry / revocation, hidden on first run
        if self._reason and self._reason not in ("not_activated", ""):
            banner = QFrame()
            banner.setStyleSheet(
                f"background: {_WARN_BG}; border: 1px solid {_WARN}; border-radius: 6px;"
            )
            bl = QVBoxLayout(banner)
            bl.setContentsMargins(14, 10, 14, 10)
            lbl = QLabel(f"⚠️  {self._reason}")
            lbl.setStyleSheet(f"color: {_WARN}; font-size: 12px;")
            lbl.setWordWrap(True)
            bl.addWidget(lbl)
            root.addWidget(banner)
            root.addSpacing(14)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_trial_tab(), "🎁  Free Trial")
        self._tabs.addTab(self._build_activate_tab(), "🔑  Activate License")
        if self._start_on_tab == "activate":
            self._tabs.setCurrentIndex(1)
        root.addWidget(self._tabs)
        root.addSpacing(16)

        # Footer
        footer = QLabel(
            "Purchased a license? Your Order ID and email are in your purchase receipt."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setWordWrap(True)
        footer.setStyleSheet(f"color: {_SUBTEXT}; font-size: 11px;")
        root.addWidget(footer)
        self.adjustSize()

    def _build_trial_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(0)

        # Feature highlights box
        box = QFrame()
        box.setStyleSheet(
            f"background: #0d2136; border: 1px solid {_TRIAL}; border-radius: 8px;"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(6)
        for feat in (
                "✅  Full access to all features for 7 days",
                "✅  Live trading, paper trading & backtesting",
                "✅  All 10 broker integrations included",
                "✅  No credit card required",
        ):
            fl = QLabel(feat)
            fl.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
            bl.addWidget(fl)
        lay.addWidget(box)
        lay.addSpacing(18)

        # Email input
        lbl = QLabel("Email Address")
        lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_SUBTEXT};")
        lay.addWidget(lbl)
        lay.addSpacing(6)

        self._trial_email = QLineEdit()
        self._trial_email.setPlaceholderText("you@example.com")
        if self._prefill_email:
            self._trial_email.setText(self._prefill_email)
        self._trial_email.returnPressed.connect(self._on_trial)
        lay.addWidget(self._trial_email)
        lay.addSpacing(14)

        # Status + spinner
        self._trial_status = QLabel("")
        self._trial_status.setAlignment(Qt.AlignCenter)
        self._trial_status.setWordWrap(True)
        self._trial_status.setStyleSheet("font-size: 12px;")
        self._trial_status.hide()
        lay.addWidget(self._trial_status)

        self._trial_spinner = QProgressBar()
        self._trial_spinner.setRange(0, 0)
        self._trial_spinner.setFixedHeight(5)
        self._trial_spinner.setStyleSheet(
            f"QProgressBar::chunk {{ background: {_TRIAL}; border-radius: 2px; }}"
        )
        self._trial_spinner.hide()
        lay.addWidget(self._trial_spinner)
        lay.addSpacing(6)

        # Button
        self._trial_btn = QPushButton("Start My Free 7-Day Trial")
        self._trial_btn.setObjectName("trialBtn")
        self._trial_btn.setFixedHeight(46)
        self._trial_btn.clicked.connect(self._on_trial)
        lay.addWidget(self._trial_btn)

        lay.addSpacing(10)
        note = QLabel("One trial per machine. No payment details needed.")
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet(f"color: {_SUBTEXT}; font-size: 11px;")
        lay.addWidget(note)
        lay.addStretch()
        return page

    def _build_activate_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(0)

        # Order ID
        lbl_o = QLabel("Order ID")
        lbl_o.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_SUBTEXT};")
        lay.addWidget(lbl_o)
        lay.addSpacing(6)

        self._order_input = QLineEdit()
        self._order_input.setPlaceholderText("e.g.  ORD-20240101-12345")
        self._order_input.returnPressed.connect(self._on_activate)
        lay.addWidget(self._order_input)
        lay.addSpacing(14)

        # Email
        lbl_e = QLabel("Email Address")
        lbl_e.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_SUBTEXT};")
        lay.addWidget(lbl_e)
        lay.addSpacing(6)

        self._activate_email = QLineEdit()
        self._activate_email.setPlaceholderText("you@example.com")
        if self._prefill_email:
            self._activate_email.setText(self._prefill_email)
        self._activate_email.returnPressed.connect(self._on_activate)
        lay.addWidget(self._activate_email)
        lay.addSpacing(14)

        # Status + spinner
        self._activate_status = QLabel("")
        self._activate_status.setAlignment(Qt.AlignCenter)
        self._activate_status.setWordWrap(True)
        self._activate_status.setStyleSheet("font-size: 12px;")
        self._activate_status.hide()
        lay.addWidget(self._activate_status)

        self._activate_spinner = QProgressBar()
        self._activate_spinner.setRange(0, 0)
        self._activate_spinner.setFixedHeight(5)
        self._activate_spinner.setStyleSheet(
            f"QProgressBar::chunk {{ background: {_ACCENT}; border-radius: 2px; }}"
        )
        self._activate_spinner.hide()
        lay.addWidget(self._activate_spinner)
        lay.addSpacing(6)

        # Button
        self._activate_btn = QPushButton("Activate License")
        self._activate_btn.setObjectName("activateBtn")
        self._activate_btn.setFixedHeight(46)
        self._activate_btn.clicked.connect(self._on_activate)
        lay.addWidget(self._activate_btn)
        lay.addStretch()
        return page

    # ── Trial slots ────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_trial(self):
        email = self._trial_email.text().strip()
        if not email or "@" not in email:
            self._set_trial_status(f"❌  Please enter a valid email address.", _ERROR)
            self._trial_email.setFocus()
            return
        self._set_trial_loading(True)
        self._set_trial_status("Contacting activation server…", _SUBTEXT)
        self._worker = _TrialWorker(email, self._manager)
        self._worker.result_ready.connect(self._on_trial_result)
        self._worker.start()

    @pyqtSlot(object)
    def _on_trial_result(self, result: LicenseResult):
        self._set_trial_loading(False)
        if result.ok:
            days = result.days_remaining or TRIAL_DURATION_DAYS
            self._set_trial_status(
                f"✅  Trial activated!  You have {days} days of full access.", _ACCENT_H
            )
            self.activation_success.emit(result)
            QTimer.singleShot(1400, self.accept)
        else:
            self._set_trial_status(f"❌  {result.reason or 'Trial activation failed.'}", _ERROR)
            # If this machine has already used its trial, switch to the paid tab after a pause
            if "already been used" in (result.reason or ""):
                QTimer.singleShot(2500, lambda: self._tabs.setCurrentIndex(1))

    # ── Paid activation slots ──────────────────────────────────────────────────

    @pyqtSlot()
    def _on_activate(self):
        order_id = self._order_input.text().strip()
        email = self._activate_email.text().strip()
        if not order_id:
            self._set_activate_status("❌  Please enter your Order ID.", _ERROR)
            self._order_input.setFocus()
            return
        if not email or "@" not in email:
            self._set_activate_status("❌  Please enter a valid email address.", _ERROR)
            self._activate_email.setFocus()
            return
        self._set_activate_loading(True)
        self._set_activate_status("Contacting activation server…", _SUBTEXT)
        self._worker = _ActivationWorker(order_id, email, self._manager)
        self._worker.result_ready.connect(self._on_activate_result)
        self._worker.start()

    @pyqtSlot(object)
    def _on_activate_result(self, result: LicenseResult):
        self._set_activate_loading(False)
        if result.ok:
            name = result.customer_name or self._activate_email.text().strip()
            self._set_activate_status(
                f"✅  Activated successfully!  Welcome, {name}.", _ACCENT_H
            )
            self.activation_success.emit(result)
            QTimer.singleShot(1400, self.accept)
        else:
            self._set_activate_status(
                f"❌  {result.reason or 'Activation failed.'}", _ERROR
            )

    # ── UI helpers ─────────────────────────────────────────────────────────────

    def _set_trial_loading(self, on: bool):
        self._trial_btn.setEnabled(not on)
        self._trial_email.setEnabled(not on)
        self._trial_spinner.setVisible(on)

    def _set_activate_loading(self, on: bool):
        self._activate_btn.setEnabled(not on)
        self._order_input.setEnabled(not on)
        self._activate_email.setEnabled(not on)
        self._activate_spinner.setVisible(on)

    def _set_trial_status(self, msg: str, color: str = _TEXT):
        self._trial_status.setText(msg)
        self._trial_status.setStyleSheet(f"font-size: 12px; color: {color};")
        self._trial_status.show()

    def _set_activate_status(self, msg: str, color: str = _TEXT):
        self._activate_status.setText(msg)
        self._activate_status.setStyleSheet(f"font-size: 12px; color: {color};")
        self._activate_status.show()


# ── TrialExpiryBanner ──────────────────────────────────────────────────────────

class TrialExpiryBanner(QFrame):
    """
    Persistent countdown banner injected at the top of the main window
    during a trial, reminding the user how many days remain.

    Turns red and shows urgent messaging when ≤ 2 days are left.

    Signals
    ───────
    upgrade_clicked — user clicked "Upgrade Now"
    dismissed       — user clicked "×"  (banner hides itself)
    """

    upgrade_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, days_remaining: int, parent=None):
        super().__init__(parent)
        self._days = days_remaining
        self._build()

    def _build(self):
        urgent = self._days <= 2
        bg = "#2d1b1e" if urgent else _WARN_BG
        border = _ERROR if urgent else _WARN
        color = _ERROR if urgent else _WARN
        icon = "🔴" if urgent else "⏳"

        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border-bottom: 2px solid {border}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 12, 8)

        if self._days == 0:
            days_text = "Trial expires <b>today</b>!"
        elif self._days == 1:
            days_text = "Trial expires <b>tomorrow</b>."
        else:
            days_text = f"Trial expires in <b>{self._days} days</b>."

        msg = QLabel(f"{icon}  {days_text}  Upgrade to keep full access.")
        msg.setStyleSheet(f"color: {color}; font-size: 12px;")
        layout.addWidget(msg, stretch=1)

        upgrade_btn = QPushButton("Upgrade Now")
        upgrade_btn.setStyleSheet(
            f"background: {_ACCENT}; color: white; border: none; "
            f"border-radius: 4px; padding: 4px 14px; "
            f"font-size: 12px; font-weight: bold;"
        )
        upgrade_btn.clicked.connect(self.upgrade_clicked.emit)
        layout.addWidget(upgrade_btn)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"background: transparent; color: {_SUBTEXT}; "
            f"border: none; font-size: 16px;"
        )
        close_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(close_btn)

    def _on_dismiss(self):
        self.dismissed.emit()
        self.hide()


# ── UpdateBanner ───────────────────────────────────────────────────────────────

class UpdateBanner(QFrame):
    """
    Dismissible blue banner shown at the top of the main window
    when an optional app update is available.
    """

    update_requested = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, version: str, notes: str, parent=None):
        super().__init__(parent)
        self._version = version
        self._notes = notes
        self._build()

    def _build(self):
        self.setStyleSheet(
            f"QFrame {{ background: #1c2128; border-bottom: 2px solid {_TRIAL}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 12, 8)

        msg = QLabel(
            f"⬆️   Version <b>{self._version}</b> is available."
            + (f"  <i>{self._notes}</i>" if self._notes else "")
        )
        msg.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        layout.addWidget(msg, stretch=1)

        btn = QPushButton("Update Now")
        btn.setStyleSheet(
            f"background: {_TRIAL}; color: white; border: none; "
            f"border-radius: 4px; padding: 4px 12px; font-size: 12px;"
        )
        btn.clicked.connect(self.update_requested.emit)
        layout.addWidget(btn)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"background: transparent; color: {_SUBTEXT}; border: none; font-size: 16px;"
        )
        close_btn.clicked.connect(lambda: (self.dismissed.emit(), self.hide()))
        layout.addWidget(close_btn)


# ── LiveTradingUpgradeDialog ──────────────────────────────────────────────────

class LiveTradingUpgradeDialog(QDialog):
    """
    Focused, in-context upsell shown the moment a free/trial user tries to
    start live trading.  Unlike the generic ActivationDialog this one is
    purpose-built for conversion:

      • Explains exactly WHY they are seeing it (they clicked Start in LIVE mode)
      • Lists what they get with a paid license
      • Has a single clear CTA: "Activate License"
      • Has a secondary "Continue in Paper Mode" escape hatch so they are
        never hard-blocked — they can always keep using the app

    Signals
    ───────
    activated          — user successfully entered order_id + email and activated
    switch_to_paper    — user chose to switch to paper mode instead of upgrading
    """

    activated = pyqtSignal(object)  # LicenseResult
    switch_to_paper = pyqtSignal()

    def __init__(self, parent=None, manager: LicenseManager = None):
        super().__init__(parent)
        self._manager = manager or license_manager
        self._worker: Optional[QThread] = None

        self.setWindowTitle("Live Trading — Upgrade Required")
        self.setModal(True)
        self.setFixedWidth(480)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(_DIALOG_CSS)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        title = QLabel("📈  Live Trading Requires a License")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        root.addSpacing(6)
        sub = QLabel(
            "Paper trading and historical backtesting are always free."
            "Activate a license to trade with real money."
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {_SUBTEXT}; font-size: 12px;")
        root.addWidget(sub)

        root.addSpacing(18)

        # ── Benefits box ───────────────────────────────────────────────────
        box = QFrame()
        box.setStyleSheet(
            f"background: #0f2a1a; border: 1px solid {_ACCENT}; border-radius: 8px;"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(6)
        for item in (
                "✅  Live trading across all 10 supported brokers",
                "✅  Automated algo + manual order placement",
                "✅  Real-time WebSocket tick data",
                "✅  1-year license  ·  1 machine",
        ):
            lbl = QLabel(item)
            lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
            bl.addWidget(lbl)
        root.addWidget(box)

        root.addSpacing(20)

        # ── Activation form ────────────────────────────────────────────────
        form = QFrame()
        form.setStyleSheet(
            f"background: {_SURFACE}; border: 1px solid {_BORDER}; border-radius: 8px;"
        )
        fl = QVBoxLayout(form)
        fl.setContentsMargins(20, 16, 20, 16)
        fl.setSpacing(10)

        lbl_o = QLabel("Order ID")
        lbl_o.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_SUBTEXT};")
        fl.addWidget(lbl_o)
        self._order_input = QLineEdit()
        self._order_input.setPlaceholderText("e.g.  ORD-20240101-12345")
        self._order_input.returnPressed.connect(self._on_activate)
        fl.addWidget(self._order_input)

        lbl_e = QLabel("Email Address")
        lbl_e.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {_SUBTEXT};")
        fl.addWidget(lbl_e)
        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("you@example.com")

        # Pre-fill email if we have it stored from a trial
        try:
            from license.license_manager import license_manager as _lm
            cached = _lm.get_cached_email()
            if cached:
                self._email_input.setText(cached)
        except Exception:
            pass

        self._email_input.returnPressed.connect(self._on_activate)
        fl.addWidget(self._email_input)

        root.addWidget(form)
        root.addSpacing(12)

        # ── Status / spinner ───────────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("font-size: 12px;")
        self._status_lbl.hide()
        root.addWidget(self._status_lbl)

        self._spinner = QProgressBar()
        self._spinner.setRange(0, 0)
        self._spinner.setFixedHeight(5)
        self._spinner.setStyleSheet(
            f"QProgressBar::chunk {{ background: {_ACCENT}; border-radius: 2px; }}"
        )
        self._spinner.hide()
        root.addWidget(self._spinner)

        root.addSpacing(8)

        # ── Primary CTA ────────────────────────────────────────────────────
        self._activate_btn = QPushButton("🔑  Activate & Enable Live Trading")
        self._activate_btn.setObjectName("activateBtn")
        self._activate_btn.setFixedHeight(46)
        self._activate_btn.clicked.connect(self._on_activate)
        root.addWidget(self._activate_btn)

        root.addSpacing(8)

        # ── Secondary escape hatch ─────────────────────────────────────────
        paper_btn = QPushButton("Continue in Paper Trading Mode Instead")
        paper_btn.setStyleSheet(
            f"background: transparent; color: {_SUBTEXT}; border: none; "
            f"font-size: 12px; text-decoration: underline;"
        )
        paper_btn.setCursor(Qt.PointingHandCursor)
        paper_btn.clicked.connect(self._on_paper)
        root.addWidget(paper_btn)

        self.adjustSize()

    # ── Slots ──────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_activate(self):
        order_id = self._order_input.text().strip()
        email = self._email_input.text().strip()
        if not order_id:
            self._show_status(f"❌  Please enter your Order ID.", _ERROR)
            self._order_input.setFocus()
            return
        if not email or "@" not in email:
            self._show_status(f"❌  Please enter a valid email address.", _ERROR)
            self._email_input.setFocus()
            return

        self._set_loading(True)
        self._show_status("Contacting activation server…", _SUBTEXT)
        self._worker = _ActivationWorker(order_id, email, self._manager)
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    @pyqtSlot(object)
    def _on_result(self, result: LicenseResult):
        self._set_loading(False)
        if result.ok:
            name = result.customer_name or self._email_input.text().strip()
            self._show_status(f"✅  Activated!  Welcome, {name}.", _ACCENT_H)
            self.activated.emit(result)
            QTimer.singleShot(1200, self.accept)
        else:
            self._show_status(f"❌  {result.reason or 'Activation failed.'}", _ERROR)

    @pyqtSlot()
    def _on_paper(self):
        self.switch_to_paper.emit()
        self.reject()

    # ── UI helpers ─────────────────────────────────────────────────────────

    def _set_loading(self, on: bool):
        self._activate_btn.setEnabled(not on)
        self._order_input.setEnabled(not on)
        self._email_input.setEnabled(not on)
        self._spinner.setVisible(on)

    def _show_status(self, msg: str, color: str = _TEXT):
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(f"font-size: 12px; color: {color};")
        self._status_lbl.show()


# ── MandatoryUpdateDialog ──────────────────────────────────────────────────────

class MandatoryUpdateDialog(QDialog):
    """Blocking dialog shown when is_mandatory=True for an app update."""

    update_requested = pyqtSignal()

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self._info = info
        self.setWindowTitle("Update Required")
        self.setModal(True)
        self.setFixedWidth(440)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)
        self.setStyleSheet(f"background: {_BG};")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("🔄  Update Required")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(
            f"Version <b>{self._info.latest_version}</b> is required to continue.<br><br>"
            f"{self._info.release_notes or 'Critical fixes and improvements are included.'}"
        )
        msg.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(8)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        self._status_lbl.hide()
        layout.addWidget(self._status_lbl)

        btn = QPushButton("Download & Install Update")
        btn.setFixedHeight(44)
        btn.setStyleSheet(
            f"background: {_ACCENT}; color: white; border: none; "
            f"border-radius: 6px; font-size: 14px; font-weight: bold;"
        )
        btn.clicked.connect(self.update_requested.emit)
        layout.addWidget(btn)

        exit_btn = QPushButton("Exit Application")
        exit_btn.setStyleSheet(
            f"background: transparent; color: {_ERROR}; border: none; font-size: 12px;"
        )
        exit_btn.clicked.connect(self.reject)
        layout.addWidget(exit_btn)
        self.adjustSize()

    def set_progress(self, percent: float, status: str = ""):
        self._progress.show()
        self._progress.setValue(int(percent))
        if status:
            self._status_lbl.setText(status)
            self._status_lbl.show()

    @pyqtSlot()
    def _on_update(self):
        self.update_requested.emit()
