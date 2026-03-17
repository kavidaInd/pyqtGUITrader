"""
ReEntrySettingGUI.py
====================
GUI dialog for configuring re-entry guard settings.

Four tabs:
  ⚙️  General   — master switch, daily cap, direction control
  ⏱️  Candles   — per-exit-reason candle wait counts with visual timeline
  💰  Price     — price-filter to avoid chasing entries
  ℹ️  Info      — explanation of every setting with scenario examples

GUI FIX: Rebuilt to match the standard ThemedDialog / ModernCard / dialog_base
pattern used by BrokerageSettingGUI, dynamic_signal_debug_popup, etc.
  • Outer wrapper is ModernCard(elevated=True)  → YELLOW_BRIGHT top accent
  • Title bar via build_title_bar()             → draggable, ghost close btn
  • Tabs via apply_tab_style()                  → YELLOW_BRIGHT selected tab
  • Buttons via create_modern_button()          → consistent hover/active
  • Section headers via create_section_header() → dot + CAPS label
  • Scroll areas styled with make_scrollbar_ss()→ slim 6-px scrollbar
  • Inner cards use ModernCard(elevated=False)  → BG_PANEL + BORDER
  • Checkbox/spin focus accent: YELLOW_BRIGHT   → matches theme
"""

import logging
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QTabWidget, QFrame, QScrollArea, QCheckBox,
    QSpinBox, QDoubleSpinBox, QSizePolicy,
)

from gui.dialog_base import (
    ThemedDialog, ModernCard,
    make_scrollbar_ss, create_section_header, create_modern_button,
    apply_tab_style, build_title_bar,
)
from gui.re_entry.ReEntrySetting import ReEntrySetting
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Small helper widgets
# ─────────────────────────────────────────────────────────────────────────────

class _HelpLabel(QLabel):
    """Muted info-box with YELLOW_BRIGHT left accent — matches other popups."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self._apply_style()
        theme_manager.theme_changed.connect(self._apply_style)
        theme_manager.density_changed.connect(self._apply_style)

    def _apply_style(self, _=None):
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
        self.setStyleSheet(f"""
            QLabel {{
                color: {c.TEXT_DIM};
                font-size: {ty.SIZE_SM}pt;
                background: {c.BG_HOVER};
                border: 1px solid {c.BORDER};
                border-left: 3px solid {c.YELLOW_BRIGHT};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
            }}
        """)


class _CandleTimelineWidget(QWidget):
    """
    Visual strip: EXIT bar → N wait candles → ENTRY bar.
    Updates dynamically as the spin-box value changes.
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._count = 3
        self._label = label
        self._build()
        theme_manager.theme_changed.connect(self._refresh)
        theme_manager.density_changed.connect(self._refresh)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        self._row_widget = QWidget()
        row = QHBoxLayout(self._row_widget)
        row.setSpacing(3)
        row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._row_widget)

        self._legend = QLabel()
        self._legend.setAlignment(Qt.AlignLeft)
        layout.addWidget(self._legend)

        self._refresh()

    def set_count(self, n: int):
        self._count = max(0, n)
        self._refresh()

    def _refresh(self, _=None):
        c = theme_manager.palette
        row = self._row_widget.layout()
        while row.count():
            item = row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def _box(text, color, tooltip):
            lbl = QLabel(text)
            lbl.setFixedSize(38, 28)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setToolTip(tooltip)
            lbl.setStyleSheet(f"""
                QLabel {{
                    background: {color};
                    color: white;
                    border-radius: 4px;
                    font-size: 8pt;
                    font-weight: bold;
                }}
            """)
            return lbl

        def _arrow():
            lbl = QLabel("→")
            lbl.setStyleSheet(
                f"color: {c.TEXT_DISABLED}; font-size: 10pt; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignCenter)
            return lbl

        row.addWidget(_box("EXIT", c.RED, "Position closed here"))
        row.addWidget(_arrow())
        for i in range(self._count):
            row.addWidget(_box(f"W{i+1}", c.TEXT_DISABLED, f"Wait candle {i+1}"))
            if i < self._count - 1:
                row.addWidget(_arrow())
        if self._count > 0:
            row.addWidget(_arrow())
        row.addWidget(_box("ENTRY", c.GREEN, "Re-entry allowed here"))
        row.addStretch()

        wait_text = (
            "immediately" if self._count == 0
            else f"after {self._count} candle{'s' if self._count != 1 else ''}"
        )
        self._legend.setText(f"  {self._label}: re-entry {wait_text} after exit")
        self._legend.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: 8pt; background: transparent; border: none;"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Dialog
# ─────────────────────────────────────────────────────────────────────────────

class ReEntrySettingGUI(ThemedDialog):
    """
    Modal dialog for configuring re-entry guard settings.

    Usage:
        dlg = ReEntrySettingGUI(reentry_setting, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            pass  # setting already saved
    """

    save_completed = pyqtSignal(bool)

    def __init__(self, setting: Optional[ReEntrySetting] = None, parent=None):
        self._safe_defaults()
        try:
            super().__init__(parent, title="RE-ENTRY SETTINGS", icon="RE", size=(900, 680))
            self.setting = setting or ReEntrySetting()
            self.setMinimumSize(680, 580)
            self.setModal(True)
            self._build_ui()
            self._load_values()
            self._connect_signals()
            self.apply_theme()
            logger.info("ReEntrySettingGUI initialized")
        except Exception as e:
            logger.critical(f"[ReEntrySettingGUI.__init__] {e}", exc_info=True)

    def _safe_defaults(self):
        self._main_card        = None
        self._tabs             = None
        self._chk_allow        = None
        self._chk_same_dir     = None
        self._chk_new_signal   = None
        self._spin_sl          = None
        self._spin_tp          = None
        self._spin_sig         = None
        self._spin_default     = None
        self._tl_sl            = None
        self._tl_tp            = None
        self._tl_sig           = None
        self._tl_default       = None
        self._chk_price_filter = None
        self._spin_price_pct   = None
        self._spin_max_day     = None
        self._status_lbl       = None
        self._save_btn         = None

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ThemedDialog sets WA_TranslucentBackground.
        # ModernCard(elevated=True) is the solid visible container —
        # exactly the same pattern as BrokerageSettingGUI.
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        self._main_card = ModernCard(self, elevated=True)
        card_lay = QVBoxLayout(self._main_card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # Title bar — draggable, monogram badge, ghost close button
        card_lay.addWidget(build_title_bar(
            self,
            title="RE-ENTRY SETTINGS",
            icon="RE",
            on_close=self.reject,
        ))

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {self._c.BORDER}; max-height: 1px;")
        card_lay.addWidget(sep)

        # Content area
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(
            self._sp.PAD_XL, self._sp.PAD_LG,
            self._sp.PAD_XL, self._sp.PAD_LG,
        )
        cl.setSpacing(self._sp.GAP_MD)

        self._tabs = self._make_tabs()
        cl.addWidget(self._tabs)

        # Status + button row
        bottom = QHBoxLayout()
        bottom.setSpacing(self._sp.GAP_SM)

        self._status_lbl = QLabel("")
        self._status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._status_lbl.setStyleSheet(f"""
            QLabel {{
                color: {self._c.TEXT_DIM};
                font-size: {self._ty.SIZE_SM}pt;
                padding: 6px 10px;
                background: {self._c.BG_HOVER};
                border-radius: {self._sp.RADIUS_MD}px;
            }}
        """)
        bottom.addWidget(self._status_lbl, 1)

        reset_btn = create_modern_button("↺  Defaults", primary=False)
        reset_btn.setToolTip("Reset all re-entry settings to factory defaults")
        reset_btn.clicked.connect(self._on_reset)
        bottom.addWidget(reset_btn)

        self._save_btn = create_modern_button("💾  Save", primary=True)
        self._save_btn.clicked.connect(self._on_save)
        bottom.addWidget(self._save_btn)

        cl.addLayout(bottom)
        card_lay.addWidget(content)
        root.addWidget(self._main_card)

    # ── Tab widget ────────────────────────────────────────────────────────────

    def _make_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        apply_tab_style(tabs)           # YELLOW_BRIGHT selected underline
        tabs.addTab(self._build_general_tab(), "⚙️  General")
        tabs.addTab(self._build_candles_tab(), "⏱️  Candles")
        tabs.addTab(self._build_price_tab(),   "💰  Price Filter")
        tabs.addTab(self._build_info_tab(),    "ℹ️  Guide")
        return tabs

    # ── Tab: General ─────────────────────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        page, lay = self._scrollable()

        # Master switch
        card1 = ModernCard()
        cl = QVBoxLayout(card1)
        cl.setSpacing(10)
        cl.addWidget(create_section_header("MASTER SWITCH"))
        self._chk_allow = self._checkbox(
            "Allow Re-Entry",
            "When enabled, the engine may re-enter a trade after a position closes.\n"
            "Disable to trade each signal only once (no re-entries ever).",
        )
        cl.addWidget(self._chk_allow)
        lay.addWidget(card1)

        # Direction
        card2 = ModernCard()
        dl = QVBoxLayout(card2)
        dl.setSpacing(10)
        dl.addWidget(create_section_header("DIRECTION CONTROL"))
        self._chk_same_dir = self._checkbox(
            "Block same-direction re-entry only",
            "ON:  after a CALL closes, only another CALL re-entry is delayed;\n"
            "     a PUT entry is still allowed immediately.\n"
            "OFF: both directions must wait (more conservative).",
        )
        dl.addWidget(self._chk_same_dir)
        lay.addWidget(card2)

        # Signal freshness
        card3 = ModernCard()
        sl = QVBoxLayout(card3)
        sl.setSpacing(10)
        sl.addWidget(create_section_header("SIGNAL FRESHNESS"))
        self._chk_new_signal = self._checkbox(
            "Require a fresh signal after the wait period",
            "ON:  re-entry only fires when the signal engine issues a NEW\n"
            "     BUY_CALL / BUY_PUT — the old signal still being active is\n"
            "     not enough.  Recommended for trailing-SL exits.\n"
            "OFF: if the original signal is still active after the candle wait,\n"
            "     re-entry fires immediately.",
        )
        sl.addWidget(self._chk_new_signal)
        lay.addWidget(card3)

        # Daily cap
        card4 = ModernCard()
        ml = QVBoxLayout(card4)
        ml.setSpacing(10)
        ml.addWidget(create_section_header("DAILY RE-ENTRY CAP"))
        row = QHBoxLayout()
        lbl = QLabel("Max re-entries per day")
        lbl.setStyleSheet(
            f"color: {self._c.TEXT_MAIN}; font-size: {self._ty.SIZE_BODY}pt; "
            f"background: transparent; border: none;"
        )
        self._spin_max_day = QSpinBox()
        self._spin_max_day.setRange(0, 50)
        self._spin_max_day.setSpecialValueText("Unlimited")
        self._spin_max_day.setToolTip(
            "0 = unlimited.\n"
            "Set e.g. 3 to allow at most 3 re-entries per session,\n"
            "regardless of how many SL/TP exits occur."
        )
        self._style_spin(self._spin_max_day)
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(self._spin_max_day)
        ml.addLayout(row)
        ml.addWidget(_HelpLabel(
            "Counts only re-entries — the first entry of the day does not count. "
            "Resets at midnight / app restart."
        ))
        lay.addWidget(card4)

        lay.addStretch()
        return page

    # ── Tab: Candles ─────────────────────────────────────────────────────────

    def _build_candles_tab(self) -> QWidget:
        page, lay = self._scrollable()

        lay.addWidget(_HelpLabel(
            "These settings control how many CLOSED candles must pass after each "
            "type of exit before a new entry is permitted.  '0' means re-entry is "
            "allowed on the very next bar."
        ))

        scenarios = [
            ("sl",      "Stop-Loss Exit",
             "Trailing SL hit on a spike?  Wait this many candles for the market "
             "to settle before re-entering."),
            ("tp",      "Take-Profit Exit",
             "Price hit TP.  Usually only 1 candle wait is enough;\n"
             "the trend may still be in your favour."),
            ("signal",  "Signal-Based Exit",
             "Exit triggered by an opposing signal (e.g. BUY_PUT flips a CALL "
             "position).  A brief cooldown avoids whipsawing."),
            ("default", "Unknown / Other Exit",
             "Fallback used when the exit reason cannot be determined."),
        ]

        for key, title, tip in scenarios:
            card = ModernCard()
            cl = QVBoxLayout(card)
            cl.setSpacing(8)
            cl.addWidget(create_section_header(title.upper()))
            cl.addWidget(_HelpLabel(tip))

            row = QHBoxLayout()
            row.setSpacing(12)
            lbl = QLabel("Wait candles:")
            lbl.setStyleSheet(
                f"color: {self._c.TEXT_MAIN}; font-size: {self._ty.SIZE_BODY}pt; "
                f"background: transparent; border: none;"
            )
            spin = QSpinBox()
            spin.setRange(0, 30)
            spin.setToolTip(f"0 = immediate re-entry after {title}")
            self._style_spin(spin)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(spin)
            cl.addLayout(row)

            tl = _CandleTimelineWidget(title)
            cl.addWidget(tl)
            lay.addWidget(card)

            if key == "sl":
                self._spin_sl,      self._tl_sl      = spin, tl
            elif key == "tp":
                self._spin_tp,      self._tl_tp      = spin, tl
            elif key == "signal":
                self._spin_sig,     self._tl_sig     = spin, tl
            elif key == "default":
                self._spin_default, self._tl_default = spin, tl

        lay.addStretch()
        return page

    # ── Tab: Price Filter ────────────────────────────────────────────────────

    def _build_price_tab(self) -> QWidget:
        page, lay = self._scrollable()

        lay.addWidget(_HelpLabel(
            "The price filter prevents the engine from chasing a re-entry at a "
            "significantly worse price than the original entry.\n\n"
            "Example: if you entered a CALL at ₹200 and it stopped out, "
            "and the price is now ₹220 (+10%), re-entry is blocked if the "
            "filter threshold is 5%."
        ))

        card = ModernCard()
        cl = QVBoxLayout(card)
        cl.setSpacing(12)
        cl.addWidget(create_section_header("PRICE-CHASE FILTER"))

        self._chk_price_filter = self._checkbox(
            "Enable price filter",
            "When ON: re-entry is blocked if the current option price is more\n"
            "than the configured % ABOVE the original entry price.",
        )
        cl.addWidget(self._chk_price_filter)

        pct_row = QHBoxLayout()
        pct_lbl = QLabel("Max price increase allowed (%)")
        pct_lbl.setStyleSheet(
            f"color: {self._c.TEXT_MAIN}; font-size: {self._ty.SIZE_BODY}pt; "
            f"background: transparent; border: none;"
        )
        self._spin_price_pct = QDoubleSpinBox()
        self._spin_price_pct.setRange(0.5, 50.0)
        self._spin_price_pct.setSingleStep(0.5)
        self._spin_price_pct.setSuffix(" %")
        self._spin_price_pct.setDecimals(1)
        self._spin_price_pct.setToolTip(
            "If the current price is more than this % above the original entry "
            "price, re-entry is blocked to avoid buying at a peak."
        )
        self._style_spin(self._spin_price_pct)
        pct_row.addWidget(pct_lbl)
        pct_row.addStretch()
        pct_row.addWidget(self._spin_price_pct)
        cl.addLayout(pct_row)

        # Worked example box — uses inner ModernCard
        ex_card = ModernCard()
        ex_lay = QVBoxLayout(ex_card)
        ex_lay.setContentsMargins(10, 10, 10, 10)
        ex_hdr = QLabel("📖  Example")
        ex_hdr.setStyleSheet(
            f"color: {self._c.YELLOW_BRIGHT}; font-size: {self._ty.SIZE_SM}pt; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        ex_body = QLabel(
            "Entry price: ₹200.  Filter: 5%.\n"
            "→  Re-entry blocked if current price > ₹210  (₹200 × 1.05).\n"
            "→  Re-entry allowed if current price ≤ ₹210."
        )
        ex_body.setWordWrap(True)
        ex_body.setStyleSheet(
            f"color: {self._c.TEXT_DIM}; font-size: {self._ty.SIZE_SM}pt; "
            f"background: transparent; border: none;"
        )
        ex_lay.addWidget(ex_hdr)
        ex_lay.addWidget(ex_body)
        cl.addWidget(ex_card)

        lay.addWidget(card)
        lay.addStretch()
        return page

    # ── Tab: Info / Guide ────────────────────────────────────────────────────

    def _build_info_tab(self) -> QWidget:
        page, lay = self._scrollable()

        sections = [
            ("🔄  WHAT IS RE-ENTRY?",
             "After any position closes (stop-loss, take-profit, or signal), the engine "
             "is normally allowed to immediately enter a new trade if the signal is still "
             "active.  This can cause problems:\n\n"
             "• A trailing stop-loss is hit on a brief price spike.  The signal is still "
             "bullish.  A re-entry at the spike high locks in a loss immediately.\n"
             "• Multiple SL exits in quick succession drain capital on the same setup.\n\n"
             "Re-Entry Guard adds a mandatory cooldown between exit and the next entry."),

            ("⏱️  CANDLE WAIT — HOW IT WORKS",
             "When a position closes, the engine records the exit time and reason "
             "(SL / TP / Signal).  On every subsequent bar completion it counts how many "
             "bars have closed since the exit.  Entry is only allowed once that count "
             "reaches the configured minimum.\n\n"
             "Each exit reason has its own counter so a tight trailing-SL exit (which "
             "benefits from more cooling-off) is treated differently from a clean TP hit "
             "(which may allow faster re-entry)."),

            ("🧭  DIRECTION CONTROL",
             "'Block same-direction only' is OFF by default (more conservative).\n\n"
             "When ON:\n"
             "  After a CALL exits → only another CALL entry is delayed.\n"
             "  A PUT entry (opposite direction) is allowed immediately.\n\n"
             "When OFF:\n"
             "  Both CALL and PUT entries are delayed for the full candle wait after "
             "either direction exits.  Use this in choppy markets."),

            ("🔔  FRESH SIGNAL REQUIREMENT",
             "'Require a fresh signal after the wait period' is ON by default.\n\n"
             "With this ON, simply waiting the minimum candles is not enough — the "
             "signal engine must produce a NEW BUY_CALL / BUY_PUT after the wait "
             "completes.  The old signal still being active at bar N+3 does NOT "
             "trigger re-entry.\n\n"
             "This prevents re-entering on stale momentum from before the SL was hit."),

            ("💰  PRICE FILTER",
             "Even after the candle wait + fresh signal, the price filter adds a "
             "final sanity check: if the option price has risen more than X% above "
             "your last entry price, the re-entry is blocked.\n\n"
             "This is especially useful for trailing-SL exits where the SL was "
             "tight and the price bounced hard — by the time the wait period ends "
             "the option could already be much more expensive than your original entry."),

            ("📊  DAILY RE-ENTRY CAP",
             "Set to 0 for unlimited re-entries (default).\n"
             "Set to a positive integer to cap re-entries per session.\n\n"
             "The cap counts only re-entries — the first trade of the day always "
             "goes through.  Useful in high-volatility sessions where you want to "
             "limit cumulative exposure from repeated SL hits."),
        ]

        for title, body_text in sections:
            card = ModernCard()
            cl = QVBoxLayout(card)
            cl.setSpacing(8)
            cl.addWidget(create_section_header(title))
            body_lbl = QLabel(body_text)
            body_lbl.setWordWrap(True)
            body_lbl.setContentsMargins(14, 6, 14, 8)
            body_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {self._c.TEXT_DIM};
                    font-size: {self._ty.SIZE_SM}pt;
                    background: transparent;
                    border: none;
                }}
            """)
            cl.addWidget(body_lbl)
            lay.addWidget(card)

        lay.addStretch()
        return page

    # ── Value loading ─────────────────────────────────────────────────────────

    def _load_values(self):
        s = self.setting
        try:
            if self._chk_allow:      self._chk_allow.setChecked(s.allow_reentry)
            if self._chk_same_dir:   self._chk_same_dir.setChecked(s.same_direction_only)
            if self._chk_new_signal: self._chk_new_signal.setChecked(s.require_new_signal)
            if self._spin_max_day:   self._spin_max_day.setValue(s.max_reentries_per_day)
            if self._spin_sl:
                self._spin_sl.setValue(s.min_candles_after_sl)
                if self._tl_sl: self._tl_sl.set_count(s.min_candles_after_sl)
            if self._spin_tp:
                self._spin_tp.setValue(s.min_candles_after_tp)
                if self._tl_tp: self._tl_tp.set_count(s.min_candles_after_tp)
            if self._spin_sig:
                self._spin_sig.setValue(s.min_candles_after_signal)
                if self._tl_sig: self._tl_sig.set_count(s.min_candles_after_signal)
            if self._spin_default:
                self._spin_default.setValue(s.min_candles_default)
                if self._tl_default: self._tl_default.set_count(s.min_candles_default)
            if self._chk_price_filter: self._chk_price_filter.setChecked(s.price_filter_enabled)
            if self._spin_price_pct:   self._spin_price_pct.setValue(s.price_filter_pct)
        except Exception as e:
            logger.error(f"[ReEntrySettingGUI._load_values] {e}", exc_info=True)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        try:
            if self._spin_sl      and self._tl_sl:
                self._spin_sl.valueChanged.connect(self._tl_sl.set_count)
            if self._spin_tp      and self._tl_tp:
                self._spin_tp.valueChanged.connect(self._tl_tp.set_count)
            if self._spin_sig     and self._tl_sig:
                self._spin_sig.valueChanged.connect(self._tl_sig.set_count)
            if self._spin_default and self._tl_default:
                self._spin_default.valueChanged.connect(self._tl_default.set_count)
            if self._chk_allow:
                self._chk_allow.toggled.connect(self._on_master_toggled)
                self._on_master_toggled(self._chk_allow.isChecked())
            self.save_completed.connect(self._on_save_completed)
        except Exception as e:
            logger.error(f"[ReEntrySettingGUI._connect_signals] {e}", exc_info=True)

    def _on_master_toggled(self, enabled: bool):
        """Dim all other tabs when master switch is off."""
        try:
            for i in range(1, self._tabs.count()):
                self._tabs.setTabEnabled(i, enabled)
        except Exception:
            pass

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_save(self):
        try:
            self._save_btn.setEnabled(False)
            s = self.setting

            s.allow_reentry         = self._chk_allow.isChecked()       if self._chk_allow        else s.allow_reentry
            s.same_direction_only   = self._chk_same_dir.isChecked()    if self._chk_same_dir     else s.same_direction_only
            s.require_new_signal    = self._chk_new_signal.isChecked()  if self._chk_new_signal   else s.require_new_signal
            s.max_reentries_per_day = self._spin_max_day.value()        if self._spin_max_day     else s.max_reentries_per_day

            s.min_candles_after_sl     = self._spin_sl.value()      if self._spin_sl      else s.min_candles_after_sl
            s.min_candles_after_tp     = self._spin_tp.value()      if self._spin_tp      else s.min_candles_after_tp
            s.min_candles_after_signal = self._spin_sig.value()     if self._spin_sig     else s.min_candles_after_signal
            s.min_candles_default      = self._spin_default.value() if self._spin_default else s.min_candles_default

            s.price_filter_enabled = self._chk_price_filter.isChecked() if self._chk_price_filter else s.price_filter_enabled
            s.price_filter_pct     = self._spin_price_pct.value()        if self._spin_price_pct   else s.price_filter_pct

            ok = s.save()
            self.save_completed.emit(ok)
        except Exception as e:
            logger.error(f"[ReEntrySettingGUI._on_save] {e}", exc_info=True)
            self.save_completed.emit(False)
        finally:
            QTimer.singleShot(300, lambda: self._save_btn.setEnabled(True) if self._save_btn else None)

    def _on_save_completed(self, ok: bool):
        if not self._status_lbl:
            return
        c, ty, sp = self._c, self._ty, self._sp
        if ok:
            self._status_lbl.setText("✅  Settings saved successfully")
            self._status_lbl.setStyleSheet(
                f"color: {c.GREEN}; font-size: {ty.SIZE_SM}pt; "
                f"padding: 6px 10px; background: {c.BG_HOVER}; "
                f"border-radius: {sp.RADIUS_MD}px;"
            )
            QTimer.singleShot(2000, self.accept)
        else:
            self._status_lbl.setText("❌  Save failed — check logs")
            self._status_lbl.setStyleSheet(
                f"color: {c.RED}; font-size: {ty.SIZE_SM}pt; "
                f"padding: 6px 10px; background: {c.BG_HOVER}; "
                f"border-radius: {sp.RADIUS_MD}px;"
            )

    def _on_reset(self):
        """Reset UI to factory defaults without saving."""
        try:
            from gui.re_entry.ReEntrySetting import ReEntrySetting as _RS
            tmp = _RS.__new__(_RS)
            tmp.data = dict(_RS.DEFAULTS)
            self.setting = tmp
            self._load_values()
            if self._status_lbl:
                self._status_lbl.setText("⚠️  Defaults loaded — click Save to apply")
                self._status_lbl.setStyleSheet(
                    f"color: {self._c.YELLOW_BRIGHT}; font-size: {self._ty.SIZE_SM}pt; "
                    f"padding: 6px 10px; background: {self._c.BG_HOVER}; "
                    f"border-radius: {self._sp.RADIUS_MD}px;"
                )
        except Exception as e:
            logger.error(f"[ReEntrySettingGUI._on_reset] {e}", exc_info=True)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self, _=None):
        """Re-apply theme when palette or density changes."""
        try:
            if self._main_card:
                self._main_card._apply_style()
            if self._tabs:
                apply_tab_style(self._tabs)
        except Exception as e:
            logger.debug(f"[ReEntrySettingGUI.apply_theme] {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _scrollable(self):
        """Return (wrapper_widget, inner_QVBoxLayout) with slim scrollbar."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(make_scrollbar_ss())

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        scroll.setWidget(container)

        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)

        return wrapper, lay

    def _checkbox(self, text: str, tooltip: str = "") -> QCheckBox:
        """Themed checkbox — checked colour matches YELLOW_BRIGHT accent."""
        cb = QCheckBox(text)
        cb.setToolTip(tooltip)
        c, ty = self._c, self._ty
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {c.BORDER};
                border-radius: 4px;
                background: {c.BG_MAIN};
            }}
            QCheckBox::indicator:checked {{
                background: {c.YELLOW_BRIGHT};
                border-color: {c.YELLOW_BRIGHT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {c.YELLOW_BRIGHT};
            }}
        """)
        return cb

    def _style_spin(self, spin):
        """Themed spin-box — focus border matches YELLOW_BRIGHT accent."""
        c, ty, sp = self._c, self._ty, self._sp
        spin.setFixedWidth(110)
        spin.setMinimumHeight(32)
        spin.setStyleSheet(f"""
            QSpinBox, QDoubleSpinBox {{
                background: {c.BG_MAIN};
                color: {c.TEXT_MAIN};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                padding: 4px 8px;
                font-size: {ty.SIZE_BODY}pt;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {c.YELLOW_BRIGHT};
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                background: {c.BG_HOVER};
                border-left: 1px solid {c.BORDER};
                border-bottom: 1px solid {c.BORDER};
                width: 18px;
            }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                background: {c.BG_HOVER};
                border-left: 1px solid {c.BORDER};
                width: 18px;
            }}
        """)