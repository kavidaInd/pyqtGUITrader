"""
gui/popups/upgrade_popup.py
============================
Upgrade prompt shown when a free/trial user attempts to enable Live Trading.
Single plan: ₹4,999 / month per user.
"""

import logging
import webbrowser

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QWidget
)

from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)

# ── Customise these ───────────────────────────────────────────────────────────
WEBSITE_SUBSCRIPTION_URL = "https://optionpilot.in/pricing"

PLAN_PRICE = "₹4,999"
PLAN_PERIOD = "/ month"
PLAN_TAGLINE = "Per user · Cancel anytime"

FEATURES = [
    ("⚡", "Real-time live execution", "Orders routed directly to your broker in milliseconds."),
    ("🛡️", "Full risk controls", "Live SL, TP, max-loss and daily trade-count limits."),
    ("📊", "Live P&L dashboard", "P&L widget and daily stats updated on every price tick."),
    ("🔗", "All supported brokers", "Works with Zerodha, Fyers, Upstox, Angel One and more."),
    ("🎯", "Algo + Manual trading", "Switch between automated signals and manual order entry."),
    ("💬", "Priority support", "Dedicated email support with faster response times."),
]


# ─────────────────────────────────────────────────────────────────────────────


class UpgradePopup(QDialog):
    """
    Shown when a free/trial user selects Live Trading in TradingModeSettingGUI.

    Usage
    -----
        popup = UpgradePopup(parent=self)
        popup.exec_()
    """

    def __init__(self, parent=None, trial_expired: bool = False):
        super().__init__(parent)
        self._trial_expired = trial_expired
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(480)
        self.setMaximumWidth(520)

        theme_manager.theme_changed.connect(self._build)
        theme_manager.density_changed.connect(self._build)
        self._build()

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self, _=None):
        old = self.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            try:
                import sip;
                sip.delete(old)
            except Exception:
                pass

        c, ty, sp = self._c, self._ty, self._sp

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        # ── main card ────────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("upgradeCard")
        card.setStyleSheet(f"""
            QFrame#upgradeCard {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER_STRONG};
                border-top: 3px solid {c.YELLOW};
                border-radius: {sp.RADIUS_LG}px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
        lay.setSpacing(sp.GAP_LG)

        # ── header ───────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(sp.GAP_MD)

        lock = QLabel("🔒")
        lock.setStyleSheet("font-size: 26px; background: transparent; border: none;")
        lock.setFixedWidth(36)

        hdr_text = QVBoxLayout()
        hdr_text.setSpacing(3)

        if self._trial_expired:
            title_text = "Your free trial has ended"
            sub_text = (
                "Your 7-day trial included live trading. "
                "Subscribe to keep trading live — Paper Trading and Backtesting remain free forever."
            )
        else:
            title_text = "Live Trading requires a subscription"
            sub_text = (
                "Paper Trading and Backtesting are always free. "
                "Subscribe to connect to a live broker and trade with real money."
            )

        title = QLabel(title_text)
        title.setStyleSheet(
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XL}pt; "
            f"font-weight: {ty.WEIGHT_HEAVY}; background: transparent; border: none;"
        )
        sub = QLabel(sub_text)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; "
            f"background: transparent; border: none;"
        )
        hdr_text.addWidget(title)
        hdr_text.addWidget(sub)
        hdr.addWidget(lock, 0, Qt.AlignTop)
        hdr.addLayout(hdr_text, 1)
        lay.addLayout(hdr)

        lay.addWidget(self._sep())

        # ── pricing block ────────────────────────────────────────────────────
        pricing = QFrame()
        pricing.setStyleSheet(f"""
            QFrame {{
                background: {c.BG_ROW_A};
                border: 1px solid {c.YELLOW};
                border-radius: {sp.RADIUS_MD}px;
            }}
        """)
        p_lay = QVBoxLayout(pricing)
        p_lay.setContentsMargins(sp.PAD_LG, sp.PAD_MD, sp.PAD_LG, sp.PAD_MD)
        p_lay.setSpacing(2)

        price_row = QHBoxLayout()
        price_row.setSpacing(6)
        price_row.setAlignment(Qt.AlignVCenter)

        amount = QLabel(PLAN_PRICE)
        amount.setStyleSheet(
            f"color: {c.YELLOW}; font-size: {ty.SIZE_2XL}pt; "
            f"font-weight: {ty.WEIGHT_HEAVY}; background: transparent; border: none;"
        )
        period = QLabel(PLAN_PERIOD)
        period.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_MD}pt; "
            f"background: transparent; border: none;"
        )
        price_row.addWidget(amount)
        price_row.addWidget(period, 0, Qt.AlignBottom)
        price_row.addStretch()

        tagline = QLabel(PLAN_TAGLINE)
        tagline.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none;"
        )

        p_lay.addLayout(price_row)
        p_lay.addWidget(tagline)
        lay.addWidget(pricing)

        # ── feature list ─────────────────────────────────────────────────────
        for icon, heading, detail in FEATURES:
            lay.addWidget(self._feature_row(icon, heading, detail))

        lay.addWidget(self._sep())

        # ── CTA button ───────────────────────────────────────────────────────
        cta = QPushButton("🚀  Subscribe Now")
        cta.setCursor(Qt.PointingHandCursor)
        cta.setMinimumHeight(46)
        cta.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c.YELLOW}, stop:1 {c.YELLOW_BRIGHT}
                );
                color: {c.TEXT_INVERSE};
                border: none;
                border-radius: {sp.RADIUS_MD}px;
                font-size: {ty.SIZE_BODY}pt;
                font-weight: {ty.WEIGHT_HEAVY};
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                letter-spacing: 0.4px;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c.YELLOW_BRIGHT}, stop:1 {c.YELLOW_BRIGHT}
                );
            }}
            QPushButton:pressed {{ background: {c.YELLOW}; }}
        """)
        cta.clicked.connect(self._on_subscribe)
        lay.addWidget(cta)

        cancel = QPushButton("Continue with Paper Trading")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c.TEXT_DIM};
                border: none;
                font-size: {ty.SIZE_SM}pt;
                padding: {sp.PAD_XS}px;
                text-decoration: underline;
            }}
            QPushButton:hover {{ color: {c.TEXT_MAIN}; }}
        """)
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel, 0, Qt.AlignCenter)

        outer.addWidget(card)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"border: none; background: {self._c.BORDER}; max-height: 1px;")
        return f

    def _feature_row(self, icon: str, heading: str, detail: str) -> QWidget:
        c, ty, sp = self._c, self._ty, self._sp
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(sp.GAP_MD)

        ic = QLabel(icon)
        ic.setFixedWidth(24)
        ic.setStyleSheet("font-size: 15px; background: transparent; border: none;")

        col = QVBoxLayout()
        col.setSpacing(0)

        h = QLabel(heading)
        h.setStyleSheet(
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_SM}pt; "
            f"font-weight: {ty.WEIGHT_BOLD}; background: transparent; border: none;"
        )
        d = QLabel(detail)
        d.setWordWrap(True)
        d.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none;"
        )
        col.addWidget(h)
        col.addWidget(d)

        row.addWidget(ic, 0, Qt.AlignTop)
        row.addLayout(col, 1)
        return w

    # ── action ────────────────────────────────────────────────────────────────

    def _on_subscribe(self):
        try:
            webbrowser.open(WEBSITE_SUBSCRIPTION_URL)
            logger.info(f"[UpgradePopup] Opened: {WEBSITE_SUBSCRIPTION_URL}")
        except Exception as e:
            logger.error(f"[UpgradePopup._on_subscribe] {e}")
        self.accept()