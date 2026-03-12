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
    LicenseManager, LicenseResult, license_manager,
    PLAN_TRIAL, PLAN_PAID, TRIAL_DURATION_DAYS,
)
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ── Theme token helpers (live — always reflects current theme) ─────────────────
def _c():   return theme_manager.palette
def _ty():  return theme_manager.typography
def _sp():  return theme_manager.spacing

# Legacy aliases kept so any external code that imports these still compiles.
# They resolve lazily at runtime so theme switches are respected.
@property
def _BG(_=None):      return _c().BG_MAIN
@property
def _SURFACE(_=None): return _c().BG_PANEL
@property
def _BORDER(_=None):  return _c().BORDER
@property
def _ACCENT(_=None):  return _c().GREEN
@property
def _ACCENT_H(_=None):return _c().GREEN_BRIGHT
@property
def _TRIAL(_=None):   return _c().BLUE_DARK
@property
def _TRIAL_H(_=None): return _c().BLUE
@property
def _TEXT(_=None):    return _c().TEXT_MAIN
@property
def _SUBTEXT(_=None): return _c().TEXT_DIM
@property
def _ERROR(_=None):   return _c().RED
@property
def _WARN(_=None):    return _c().YELLOW
@property
def _WARN_BG(_=None): return _c().YELLOW_GLOW


def _dialog_css() -> str:
    """Build the shared dialog stylesheet from live theme tokens."""
    c  = _c()
    ty = _ty()
    sp = _sp()
    return f"""
        QDialog {{
            background: {c.BG_MAIN};
        }}
        QLabel {{
            color: {c.TEXT_MAIN};
            background: transparent;
        }}
        QTabWidget::pane {{
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: 0 {sp.RADIUS_MD}px {sp.RADIUS_MD}px {sp.RADIUS_MD}px;
            background: {c.BG_PANEL};
        }}
        QTabBar::tab {{
            background: {c.BG_MAIN};
            color: {c.TEXT_DIM};
            padding: {sp.PAD_MD}px 0;
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-bottom: none;
            border-top-left-radius: {sp.RADIUS_MD}px;
            border-top-right-radius: {sp.RADIUS_MD}px;
            font-size: {ty.SIZE_BODY}pt;
            font-weight: {ty.WEIGHT_BOLD};
            min-width: 170px;
        }}
        QTabBar::tab:selected {{
            background: {c.BG_PANEL};
            color: {c.TEXT_BRIGHT};
            border-bottom: 2px solid {c.BLUE};
        }}
        QLineEdit {{
            background: {c.BG_INPUT};
            color: {c.TEXT_MAIN};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_MD}px;
            padding: {sp.PAD_MD}px {sp.PAD_LG}px;
            font-size: {ty.SIZE_BODY}pt;
            min-height: {sp.INPUT_HEIGHT}px;
            selection-background-color: {c.BG_SELECTED};
        }}
        QLineEdit:focus {{
            border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
        }}
        QPushButton#trialBtn {{
            background: {c.BLUE_DARK};
            color: {c.TEXT_INVERSE};
            border: none;
            border-radius: {sp.RADIUS_MD}px;
            padding: {sp.PAD_MD}px {sp.PAD_XL}px;
            font-size: {ty.SIZE_MD}pt;
            font-weight: {ty.WEIGHT_BOLD};
        }}
        QPushButton#trialBtn:hover    {{ background: {c.BLUE}; }}
        QPushButton#trialBtn:disabled {{ background: {c.BG_CARD}; color: {c.TEXT_DISABLED}; }}
        QPushButton#activateBtn {{
            background: {c.GREEN};
            color: {c.TEXT_INVERSE};
            border: none;
            border-radius: {sp.RADIUS_MD}px;
            padding: {sp.PAD_MD}px {sp.PAD_XL}px;
            font-size: {ty.SIZE_MD}pt;
            font-weight: {ty.WEIGHT_BOLD};
        }}
        QPushButton#activateBtn:hover    {{ background: {c.GREEN_BRIGHT}; }}
        QPushButton#activateBtn:disabled {{ background: {c.BG_CARD}; color: {c.TEXT_DISABLED}; }}
        QProgressBar {{
            background: {c.BG_PANEL};
            border: {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: {sp.RADIUS_SM}px;
            height: 5px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            border-radius: {sp.RADIUS_SM}px;
        }}
    """


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
        self.setStyleSheet(_dialog_css())
        theme_manager.theme_changed.connect(lambda _=None: self.setStyleSheet(_dialog_css()))
        theme_manager.density_changed.connect(lambda _=None: self.setStyleSheet(_dialog_css()))
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        c  = _c()
        ty = _ty()
        sp = _sp()

        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_2XL, sp.PAD_XL + 4, sp.PAD_2XL, sp.PAD_XL + 4)
        root.setSpacing(0)

        # Header
        title = QLabel("🚀  Algo Trading Pro")
        title.setFont(QFont(ty.FONT_UI, ty.SIZE_2XL, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        root.addSpacing(sp.GAP_SM)
        tagline = QLabel("Professional algorithmic trading — start free, upgrade anytime")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt;")
        root.addWidget(tagline)
        root.addSpacing(sp.GAP_XL)

        # Reason banner — shown for expiry / revocation, hidden on first run
        if self._reason and self._reason not in ("not_activated", ""):
            banner = QFrame()
            banner.setStyleSheet(
                f"background: {c.YELLOW_GLOW}; border: 1px solid {c.YELLOW}; "
                f"border-radius: {sp.RADIUS_MD}px;"
            )
            bl = QVBoxLayout(banner)
            bl.setContentsMargins(sp.PAD_MD, sp.PAD_SM + 2, sp.PAD_MD, sp.PAD_SM + 2)
            lbl = QLabel(f"⚠️  {self._reason}")
            lbl.setStyleSheet(f"color: {c.YELLOW_BRIGHT}; font-size: {ty.SIZE_SM}pt;")
            lbl.setWordWrap(True)
            bl.addWidget(lbl)
            root.addWidget(banner)
            root.addSpacing(sp.GAP_LG)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_trial_tab(), "🎁  Free Trial")
        self._tabs.addTab(self._build_activate_tab(), "🔑  Activate License")
        if self._start_on_tab == "activate":
            self._tabs.setCurrentIndex(1)
        root.addWidget(self._tabs)
        root.addSpacing(sp.GAP_LG)

        # Footer
        footer = QLabel(
            "Purchased a license? Your Order ID and email are in your purchase receipt."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setWordWrap(True)
        footer.setStyleSheet(f"color: {c.TEXT_MUTED}; font-size: {ty.SIZE_XS}pt;")
        root.addWidget(footer)
        self.adjustSize()

    def _build_trial_tab(self) -> QWidget:
        c  = _c()
        ty = _ty()
        sp = _sp()

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        lay.setSpacing(0)

        # Feature highlights box
        box = QFrame()
        box.setStyleSheet(
            f"background: {c.BLUE_GLOW}; border: 1px solid {c.BLUE}; "
            f"border-radius: {sp.RADIUS_LG}px;"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(sp.PAD_MD, sp.PAD_SM + 4, sp.PAD_MD, sp.PAD_SM + 4)
        bl.setSpacing(sp.GAP_SM)
        for feat in (
                "✅  Full access to all features for 7 days",
                "✅  Live trading with real broker connectivity",
                "✅  Paper trading & backtesting included",
                "✅  All supported broker integrations",
                "✅  No credit card required",
        ):
            fl = QLabel(feat)
            fl.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}pt;")
            bl.addWidget(fl)
        lay.addWidget(box)
        lay.addSpacing(sp.GAP_LG)

        # Email input
        lbl = QLabel("Email Address")
        lbl.setStyleSheet(
            f"font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD}; color: {c.TEXT_DIM};"
        )
        lay.addWidget(lbl)
        lay.addSpacing(sp.GAP_SM)

        self._trial_email = QLineEdit()
        self._trial_email.setPlaceholderText("you@example.com")
        if self._prefill_email:
            self._trial_email.setText(self._prefill_email)
        self._trial_email.returnPressed.connect(self._on_trial)
        lay.addWidget(self._trial_email)
        lay.addSpacing(sp.GAP_LG)

        # Status + spinner
        self._trial_status = QLabel("")
        self._trial_status.setAlignment(Qt.AlignCenter)
        self._trial_status.setWordWrap(True)
        self._trial_status.setStyleSheet(f"font-size: {ty.SIZE_SM}pt;")
        self._trial_status.hide()
        lay.addWidget(self._trial_status)

        self._trial_spinner = QProgressBar()
        self._trial_spinner.setRange(0, 0)
        self._trial_spinner.setFixedHeight(5)
        self._trial_spinner.setStyleSheet(
            f"QProgressBar::chunk {{ background: {c.BLUE}; border-radius: 2px; }}"
        )
        self._trial_spinner.hide()
        lay.addWidget(self._trial_spinner)
        lay.addSpacing(sp.GAP_SM)

        # Button
        self._trial_btn = QPushButton("Start My Free 7-Day Trial")
        self._trial_btn.setObjectName("trialBtn")
        self._trial_btn.setFixedHeight(sp.BTN_HEIGHT_LG)
        self._trial_btn.clicked.connect(self._on_trial)
        lay.addWidget(self._trial_btn)

        lay.addSpacing(sp.PAD_MD)
        note = QLabel("One 7-day trial per machine. After trial, upgrade for ₹4,999/month.")
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet(f"color: {c.TEXT_MUTED}; font-size: {ty.SIZE_XS}pt;")
        lay.addWidget(note)
        lay.addStretch()
        return page
    def _build_activate_tab(self) -> QWidget:
        c  = _c()
        ty = _ty()
        sp = _sp()

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        lay.setSpacing(0)

        # Order ID
        lbl_o = QLabel("Order ID")
        lbl_o.setStyleSheet(
            f"font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD}; color: {c.TEXT_DIM};"
        )
        lay.addWidget(lbl_o)
        lay.addSpacing(sp.GAP_SM)

        self._order_input = QLineEdit()
        self._order_input.setPlaceholderText("e.g.  ORD-20240101-12345")
        self._order_input.returnPressed.connect(self._on_activate)
        lay.addWidget(self._order_input)
        lay.addSpacing(sp.GAP_LG)

        # Email
        lbl_e = QLabel("Email Address")
        lbl_e.setStyleSheet(
            f"font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD}; color: {c.TEXT_DIM};"
        )
        lay.addWidget(lbl_e)
        lay.addSpacing(sp.GAP_SM)

        self._activate_email = QLineEdit()
        self._activate_email.setPlaceholderText("you@example.com")
        if self._prefill_email:
            self._activate_email.setText(self._prefill_email)
        self._activate_email.returnPressed.connect(self._on_activate)
        lay.addWidget(self._activate_email)
        lay.addSpacing(sp.GAP_LG)

        # Status + spinner
        self._activate_status = QLabel("")
        self._activate_status.setAlignment(Qt.AlignCenter)
        self._activate_status.setWordWrap(True)
        self._activate_status.setStyleSheet(f"font-size: {ty.SIZE_SM}pt;")
        self._activate_status.hide()
        lay.addWidget(self._activate_status)

        self._activate_spinner = QProgressBar()
        self._activate_spinner.setRange(0, 0)
        self._activate_spinner.setFixedHeight(5)
        self._activate_spinner.setStyleSheet(
            f"QProgressBar::chunk {{ background: {c.GREEN}; border-radius: 2px; }}"
        )
        self._activate_spinner.hide()
        lay.addWidget(self._activate_spinner)
        lay.addSpacing(sp.GAP_SM)

        # Button
        self._activate_btn = QPushButton("Activate License")
        self._activate_btn.setObjectName("activateBtn")
        self._activate_btn.setFixedHeight(sp.BTN_HEIGHT_LG)
        self._activate_btn.clicked.connect(self._on_activate)
        lay.addWidget(self._activate_btn)
        lay.addStretch()
        return page

    # ── Trial slots ────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_trial(self):
        c = _c()
        email = self._trial_email.text().strip()
        if not email or "@" not in email:
            self._set_trial_status("❌  Please enter a valid email address.", c.RED)
            self._trial_email.setFocus()
            return
        self._set_trial_loading(True)
        self._set_trial_status("Contacting activation server…", c.TEXT_DIM)
        self._worker = _TrialWorker(email, self._manager)
        self._worker.result_ready.connect(self._on_trial_result)
        self._worker.start()

    @pyqtSlot(object)
    def _on_trial_result(self, result: LicenseResult):
        c = _c()
        self._set_trial_loading(False)
        if result.ok:
            days = result.days_remaining or TRIAL_DURATION_DAYS
            self._set_trial_status(
                f"✅  Trial activated!  You have {days} days of full access.", c.GREEN_BRIGHT
            )
            self.activation_success.emit(result)
            QTimer.singleShot(1400, self.accept)
        else:
            self._set_trial_status(f"❌  {result.reason or 'Trial activation failed.'}", c.RED)
            # If this machine has already used its trial, switch to the paid tab after a pause
            if "already been used" in (result.reason or ""):
                QTimer.singleShot(2500, lambda: self._tabs.setCurrentIndex(1))

    # ── Paid activation slots ──────────────────────────────────────────────────

    @pyqtSlot()
    def _on_activate(self):
        c = _c()
        order_id = self._order_input.text().strip()
        email = self._activate_email.text().strip()
        if not order_id:
            self._set_activate_status("❌  Please enter your Order ID.", c.RED)
            self._order_input.setFocus()
            return
        if not email or "@" not in email:
            self._set_activate_status("❌  Please enter a valid email address.", c.RED)
            self._activate_email.setFocus()
            return
        self._set_activate_loading(True)
        self._set_activate_status("Contacting activation server…", c.TEXT_DIM)
        self._worker = _ActivationWorker(order_id, email, self._manager)
        self._worker.result_ready.connect(self._on_activate_result)
        self._worker.start()

    @pyqtSlot(object)
    def _on_activate_result(self, result: LicenseResult):
        c = _c()
        self._set_activate_loading(False)
        if result.ok:
            name = result.customer_name or self._activate_email.text().strip()
            self._set_activate_status(
                f"✅  Activated successfully!  Welcome, {name}.", c.GREEN_BRIGHT
            )
            self.activation_success.emit(result)
            QTimer.singleShot(1400, self.accept)
        else:
            self._set_activate_status(
                f"❌  {result.reason or 'Activation failed.'}", c.RED
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

    def _set_trial_status(self, msg: str, color: str = ""):
        ty = _ty()
        color = color or _c().TEXT_MAIN
        self._trial_status.setText(msg)
        self._trial_status.setStyleSheet(f"font-size: {ty.SIZE_SM}pt; color: {color};")
        self._trial_status.show()

    def _set_activate_status(self, msg: str, color: str = ""):
        ty = _ty()
        color = color or _c().TEXT_MAIN
        self._activate_status.setText(msg)
        self._activate_status.setStyleSheet(f"font-size: {ty.SIZE_SM}pt; color: {color};")
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
        theme_manager.theme_changed.connect(lambda _=None: self._rebuild())
        theme_manager.density_changed.connect(lambda _=None: self._rebuild())

    def _rebuild(self):
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._build()

    def _build(self):
        c  = _c()
        ty = _ty()
        sp = _sp()

        urgent = self._days <= 2
        bg     = c.RED_GLOW   if urgent else c.YELLOW_GLOW
        border = c.RED        if urgent else c.YELLOW
        color  = c.RED_BRIGHT if urgent else c.YELLOW_BRIGHT
        icon   = "🔴" if urgent else "⏳"

        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border-bottom: 2px solid {border}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)

        if self._days == 0:
            days_text = "Trial expires <b>today</b>!"
        elif self._days == 1:
            days_text = "Trial expires <b>tomorrow</b>."
        else:
            days_text = f"Trial expires in <b>{self._days} days</b>."

        msg = QLabel(f"{icon}  {days_text}  Upgrade to keep full access.")
        msg.setStyleSheet(f"color: {color}; font-size: {ty.SIZE_SM}pt;")
        layout.addWidget(msg, stretch=1)

        upgrade_btn = QPushButton("Upgrade Now")
        upgrade_btn.setStyleSheet(
            f"background: {c.GREEN}; color: {c.TEXT_INVERSE}; border: none; "
            f"border-radius: {sp.RADIUS_SM}px; padding: {sp.PAD_XS}px {sp.PAD_MD}px; "
            f"font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        upgrade_btn.clicked.connect(self.upgrade_clicked.emit)
        layout.addWidget(upgrade_btn)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(sp.ICON_XL, sp.ICON_XL)
        close_btn.setStyleSheet(
            f"background: transparent; color: {c.TEXT_DIM}; "
            f"border: none; font-size: {ty.SIZE_LG}pt;"
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

    @property
    def _c(self): return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def _build(self):
        c, sp, ty = self._c, self._sp, self._ty
        self.setStyleSheet(
            f"QFrame {{ background: {c.BG_PANEL}; border-bottom: 2px solid {c.BLUE_DARK}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp.PAD_LG, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)

        msg = QLabel(
            f"⬆️   Version <b>{self._version}</b> is available."
            + (f"  <i>{self._notes}</i>" if self._notes else "")
        )
        msg.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}px;")
        layout.addWidget(msg, stretch=1)

        btn = QPushButton("Update Now")
        btn.setStyleSheet(
            f"background: {c.BLUE_DARK}; color: white; border: none; "
            f"border-radius: {sp.RADIUS_SM}px; padding: {sp.PAD_XS}px {sp.PAD_MD}px; "
            f"font-size: {ty.SIZE_SM}px;"
        )
        btn.clicked.connect(self.update_requested.emit)
        layout.addWidget(btn)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"background: transparent; color: {c.TEXT_DIM}; border: none; "
            f"font-size: {ty.SIZE_BODY}px;"
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
        self.setStyleSheet(_dialog_css())
        theme_manager.theme_changed.connect(self._on_theme)
        theme_manager.density_changed.connect(self._on_theme)
        self._build()

    @property
    def _c(self): return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def _on_theme(self):
        self.setStyleSheet(_dialog_css())

    def _build(self):
        c, sp, ty = self._c, self._sp, self._ty
        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────
        title = QLabel("📈  Live Trading Requires a License")
        title.setFont(QFont(ty.FAMILY, ty.SIZE_H2, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        root.addSpacing(sp.GAP_SM)
        sub = QLabel(
            "Paper trading and backtesting are always free. "
            "Your 7-day trial has ended — subscribe to resume live trading."
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}px;")
        root.addWidget(sub)

        root.addSpacing(sp.GAP_LG)

        # ── Benefits box ───────────────────────────────────────────────────
        box = QFrame()
        box.setStyleSheet(
            f"background: {c.GREEN_GLOW}; border: 1px solid {c.GREEN}; "
            f"border-radius: {sp.RADIUS_MD}px;"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(sp.PAD_LG, sp.PAD_MD, sp.PAD_LG, sp.PAD_MD)
        bl.setSpacing(sp.GAP_SM)
        for item in (
                "✅  Live trading across all supported brokers",
                "✅  Automated algo + manual order placement",
                "✅  Real-time WebSocket tick data & live P&L",
                "✅  Full risk controls — SL, TP, max-loss limits",
                "✅  ₹4,999 / month · Cancel anytime",
        ):
            lbl = QLabel(item)
            lbl.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}px;")
            bl.addWidget(lbl)
        root.addWidget(box)

        root.addSpacing(sp.GAP_LG)

        # ── Activation form ────────────────────────────────────────────────
        form = QFrame()
        form.setStyleSheet(
            f"background: {c.BG_PANEL}; border: 1px solid {c.BORDER}; "
            f"border-radius: {sp.RADIUS_MD}px;"
        )
        fl = QVBoxLayout(form)
        fl.setContentsMargins(sp.PAD_LG, sp.PAD_MD, sp.PAD_LG, sp.PAD_MD)
        fl.setSpacing(sp.GAP_MD)

        lbl_o = QLabel("Order ID")
        lbl_o.setStyleSheet(
            f"font-size: {ty.SIZE_SM}px; font-weight: bold; color: {c.TEXT_DIM};"
        )
        fl.addWidget(lbl_o)
        self._order_input = QLineEdit()
        self._order_input.setPlaceholderText("e.g.  ORD-20240101-12345")
        self._order_input.returnPressed.connect(self._on_activate)
        fl.addWidget(self._order_input)

        lbl_e = QLabel("Email Address")
        lbl_e.setStyleSheet(
            f"font-size: {ty.SIZE_SM}px; font-weight: bold; color: {c.TEXT_DIM};"
        )
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
        root.addSpacing(sp.GAP_MD)

        # ── Status / spinner ───────────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(f"font-size: {ty.SIZE_SM}px;")
        self._status_lbl.hide()
        root.addWidget(self._status_lbl)

        self._spinner = QProgressBar()
        self._spinner.setRange(0, 0)
        self._spinner.setFixedHeight(5)
        self._spinner.setStyleSheet(
            f"QProgressBar::chunk {{ background: {c.GREEN}; "
            f"border-radius: {sp.RADIUS_XS}px; }}"
        )
        self._spinner.hide()
        root.addWidget(self._spinner)

        root.addSpacing(sp.GAP_SM)

        # ── Primary CTA ────────────────────────────────────────────────────
        self._activate_btn = QPushButton("🔑  Activate & Enable Live Trading")
        self._activate_btn.setObjectName("activateBtn")
        self._activate_btn.setFixedHeight(sp.BTN_HEIGHT_LG)
        self._activate_btn.clicked.connect(self._on_activate)
        root.addWidget(self._activate_btn)

        root.addSpacing(sp.GAP_SM)

        # ── Secondary escape hatch ─────────────────────────────────────────
        paper_btn = QPushButton("Continue in Paper Trading Mode Instead")
        paper_btn.setStyleSheet(
            f"background: transparent; color: {c.TEXT_DIM}; border: none; "
            f"font-size: {ty.SIZE_SM}px; text-decoration: underline;"
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
        self._show_status("Contacting activation server…", self._c.TEXT_DIM)
        self._worker = _ActivationWorker(order_id, email, self._manager)
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    @pyqtSlot(object)
    def _on_result(self, result: LicenseResult):
        self._set_loading(False)
        if result.ok:
            name = result.customer_name or self._email_input.text().strip()
            self._show_status(f"✅  Activated!  Welcome, {name}.", self._c.GREEN_BRIGHT)
            self.activated.emit(result)
            QTimer.singleShot(1200, self.accept)
        else:
            self._show_status(f"❌  {result.reason or 'Activation failed.'}", self._c.RED)

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

    def _show_status(self, msg: str, color: str = ""):
        if not color:
            color = self._c.TEXT_MAIN
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"font-size: {self._ty.SIZE_SM}px; color: {color};"
        )
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
        self.setStyleSheet(f"background: {theme_manager.palette.BG_MAIN};")
        theme_manager.theme_changed.connect(self._on_theme)
        theme_manager.density_changed.connect(self._on_theme)
        self._build()

    @property
    def _c(self): return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def _on_theme(self):
        self.setStyleSheet(f"background: {self._c.BG_MAIN};")

    def _build(self):
        c, sp, ty = self._c, self._sp, self._ty
        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        layout.setSpacing(sp.GAP_LG)

        title = QLabel("🔄  Update Required")
        title.setFont(QFont(ty.FAMILY, ty.SIZE_H2, QFont.Bold))
        title.setStyleSheet(f"color: {c.TEXT_MAIN};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(
            f"Version <b>{self._info.latest_version}</b> is required to continue.<br><br>"
            f"{self._info.release_notes or 'Critical fixes and improvements are included.'}"
        )
        msg.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_BODY}px;")
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
        self._status_lbl.setStyleSheet(f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}px;")
        self._status_lbl.hide()
        layout.addWidget(self._status_lbl)

        btn = QPushButton("Download & Install Update")
        btn.setFixedHeight(sp.BTN_HEIGHT_LG)
        btn.setStyleSheet(
            f"background: {c.GREEN}; color: white; border: none; "
            f"border-radius: {sp.RADIUS_MD}px; font-size: {ty.SIZE_BODY}px; font-weight: bold;"
        )
        btn.clicked.connect(self.update_requested.emit)
        layout.addWidget(btn)

        exit_btn = QPushButton("Exit Application")
        exit_btn.setStyleSheet(
            f"background: transparent; color: {c.RED}; border: none; "
            f"font-size: {ty.SIZE_SM}px;"
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