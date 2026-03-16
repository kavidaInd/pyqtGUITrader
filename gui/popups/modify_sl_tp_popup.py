"""
gui/popups/modify_sl_tp_popup.py
=================================
Popups for live-trade modification: Stop-Loss, Take-Profit, and Exit confirmation.

All three dialogs match the app design language exactly:
  • ThemedDialog base  (FramelessWindowHint + WA_TranslucentBackground)
  • ModernCard(elevated=True) wrapper  (YELLOW_BRIGHT top border, BG_MAIN body)
  • build_title_bar()  (monogram badge + CAPS title + ghost close button)
  • create_modern_button()  (shared button factory — primary / danger / ghost)
  • All colours exclusively from theme_manager — live theme-switch aware
"""

import logging

from PyQt5.QtCore    import Qt
from PyQt5.QtGui     import QDoubleValidator
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QWidget,
)

from data.trade_state_manager import state_manager
from gui.dialog_base import (
    ThemedDialog, ModernCard, build_title_bar, create_modern_button,
)
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers  (shared by all three dialogs)
# ─────────────────────────────────────────────────────────────────────────────

def _sep(c) -> QFrame:
    """1-px horizontal divider."""
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {c.BORDER}; border: none;")
    return f


def _info_row(label: str, value: str, value_color=None, *, c, ty) -> QWidget:
    """Key  ···  Value row used inside summary cards."""
    vc = value_color or c.TEXT_MAIN
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)

    lbl_w = QLabel(label)
    lbl_w.setStyleSheet(
        f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; "
        f"background: transparent; border: none;"
    )
    lay.addWidget(lbl_w)
    lay.addStretch()

    val_w = QLabel(value)
    val_w.setStyleSheet(
        f"color: {vc}; font-size: {ty.SIZE_SM}pt; "
        f"font-weight: bold; background: transparent; border: none;"
    )
    lay.addWidget(val_w)
    return w


def _section_label(text: str, *, c, ty) -> QLabel:
    """All-caps section label placed above an input field."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_XS}pt; "
        f"letter-spacing: 0.8px; font-weight: bold; "
        f"background: transparent; border: none;"
    )
    return lbl


def _input_field(placeholder: str, default: str, *, c, ty, sp) -> QLineEdit:
    """Themed numeric input with focus ring."""
    h = getattr(sp, "INPUT_HEIGHT", 36)
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setText(default)
    inp.setValidator(QDoubleValidator(0.01, 9999.99, 2, inp))
    inp.setFixedHeight(h)
    inp.setStyleSheet(f"""
        QLineEdit {{
            background:    {c.BG_INPUT};
            color:         {c.TEXT_MAIN};
            border:        1px solid {c.BORDER};
            border-radius: {sp.RADIUS_MD}px;
            padding:       0 12px;
            font-size:     {ty.SIZE_BODY}pt;
            selection-background-color: {c.BG_SELECTED};
        }}
        QLineEdit:focus  {{ border-color: {c.BORDER_FOCUS}; }}
        QLineEdit:hover  {{ border-color: {c.BORDER_STRONG}; }}
    """)
    return inp


def _preview_lbl(color: str, *, c, ty) -> QLabel:
    """Live preview / error label rendered below the input."""
    lbl = QLabel("")
    lbl.setWordWrap(True)
    lbl.setMinimumHeight(20)
    lbl.setStyleSheet(
        f"color: {color}; font-size: {ty.SIZE_SM}pt; "
        f"font-weight: bold; background: transparent; border: none;"
    )
    return lbl


def _summary_card(rows: list, *, c, ty, sp) -> QFrame:
    """
    BG_PANEL rounded card containing multiple _info_row widgets.
    `rows` — list of (label, value) or (label, value, color) tuples.
    """
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background:    {c.BG_PANEL};
            border:        1px solid {c.BORDER};
            border-radius: {sp.RADIUS_MD}px;
        }}
    """)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(sp.PAD_MD, sp.PAD_SM + 2, sp.PAD_MD, sp.PAD_SM + 2)
    lay.setSpacing(sp.GAP_XS + 2)
    for row in rows:
        label, value = row[0], row[1]
        color = row[2] if len(row) > 2 else None
        lay.addWidget(_info_row(label, value, color, c=c, ty=ty))
    return card


def _warn_card(text: str, *, c, ty, sp) -> QFrame:
    """Yellow-accented warning note card."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background:    {c.YELLOW_BRIGHT}14;
            border:        1px solid {c.YELLOW_BRIGHT}55;
            border-left:   3px solid {c.YELLOW_BRIGHT};
            border-radius: {sp.RADIUS_SM}px;
        }}
    """)
    lay = QHBoxLayout(card)
    lay.setContentsMargins(sp.PAD_SM, sp.PAD_XS + 2, sp.PAD_SM, sp.PAD_XS + 2)
    lay.setSpacing(sp.GAP_SM)

    icon = QLabel("⚠")
    icon.setStyleSheet(
        f"color: {c.YELLOW_BRIGHT}; font-size: {ty.SIZE_BODY}pt; "
        f"background: transparent; border: none;"
    )
    lay.addWidget(icon, 0, Qt.AlignTop)

    msg = QLabel(text)
    msg.setWordWrap(True)
    msg.setStyleSheet(
        f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; "
        f"background: transparent; border: none;"
    )
    lay.addWidget(msg, 1)
    return card


# ─────────────────────────────────────────────────────────────────────────────
# ModifyTPDialog
# ─────────────────────────────────────────────────────────────────────────────

class ModifyTPDialog(ThemedDialog):
    """Update Take-Profit % for the current open trade."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="MODIFY TAKE-PROFIT",
            icon="TP",
            size=(380, 490),
        )
        self._snapshot = state_manager.get_position_snapshot()
        self._build_ui()
        self.apply_theme()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        c, ty, sp = self._c, self._ty, self._sp

        # Shadow margin → card fills centre
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        self.main_card = ModernCard(self, elevated=True)
        ml = QVBoxLayout(self.main_card)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        ml.addWidget(build_title_bar(
            self, "MODIFY TAKE-PROFIT", icon="TP",
            on_close=self.reject,
        ))

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        bl.setSpacing(sp.GAP_MD)

        # Current trade context
        entry      = self._snapshot.get("current_buy_price")
        cur_tp     = self._snapshot.get("tp_point")
        cur_tp_pct = float(getattr(state_manager.get_state(), "tp_percentage", 2.0))

        rows = []
        if entry is not None:
            rows.append(("Entry Price", f"₹{float(entry):.2f}"))
        if cur_tp is not None:
            rows.append(("Current Target", f"₹{float(cur_tp):.2f}", c.GREEN))
        rows.append(("Current TP %", f"{cur_tp_pct:.1f}%", c.GREEN))
        bl.addWidget(_summary_card(rows, c=c, ty=ty, sp=sp))

        bl.addWidget(_sep(c))

        bl.addWidget(_section_label("New Take-Profit %", c=c, ty=ty))

        self._input = _input_field(
            f"e.g. {cur_tp_pct:.1f}", f"{cur_tp_pct:.1f}",
            c=c, ty=ty, sp=sp,
        )
        self._input.selectAll()
        bl.addWidget(self._input)

        self._preview = _preview_lbl(c.GREEN, c=c, ty=ty)
        bl.addWidget(self._preview)
        self._input.textChanged.connect(self._update_preview)
        self._update_preview(self._input.text())

        bl.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)
        cancel_btn      = create_modern_button("Cancel")
        self._apply_btn = create_modern_button("Apply", primary=True, icon="✓")
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._apply_btn)
        bl.addLayout(btn_row)

        ml.addWidget(body, 1)
        root.addWidget(self.main_card)

    # ── logic ─────────────────────────────────────────────────────────────────

    def _update_preview(self, text: str):
        try:
            pct   = float(text)
            entry = self._snapshot.get("current_buy_price")
            if entry and pct > 0:
                tp = float(entry) * (1 + pct / 100)
                self._preview.setText(f"→ New TP target: ₹{tp:.2f}")
                self._preview.setStyleSheet(
                    f"color: {self._c.GREEN}; font-size: {self._ty.SIZE_SM}pt; "
                    f"font-weight: bold; background: transparent; border: none;"
                )
            else:
                self._preview.setText("")
        except (ValueError, TypeError):
            self._preview.setText("")

    def _on_apply(self):
        try:
            pct = float(self._input.text())
            if pct <= 0:
                self._show_error("TP % must be greater than 0")
                return
            state = state_manager.get_state()
            state.tp_percentage = pct
            entry = state.current_buy_price
            if entry is not None:
                state.tp_point = float(entry) * (1 + pct / 100)
                logger.info(f"[ModifyTPDialog] TP updated: {pct:.1f}% → ₹{state.tp_point:.2f}")
            else:
                state.tp_point = None
            self.accept()
        except (ValueError, TypeError):
            self._show_error("Please enter a valid percentage")
        except Exception as e:
            logger.error(f"[ModifyTPDialog._on_apply] {e}", exc_info=True)
            self._show_error(f"Failed to update TP: {e}")

    def _show_error(self, msg: str):
        self._preview.setStyleSheet(
            f"color: {self._c.RED_BRIGHT}; font-size: {self._ty.SIZE_SM}pt; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        self._preview.setText(f"⚠  {msg}")

    def apply_theme(self, _=None):
        try:
            if hasattr(self, "main_card") and self.main_card:
                self.main_card._apply_style()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# ModifySLDialog
# ─────────────────────────────────────────────────────────────────────────────

class ModifySLDialog(ThemedDialog):
    """Update Stop-Loss % for the current open trade."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="MODIFY STOP-LOSS",
            icon="SL",
            size=(380, 490),
        )
        self._snapshot = state_manager.get_position_snapshot()
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        c, ty, sp = self._c, self._ty, self._sp

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        self.main_card = ModernCard(self, elevated=True)
        ml = QVBoxLayout(self.main_card)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        ml.addWidget(build_title_bar(
            self, "MODIFY STOP-LOSS", icon="SL",
            on_close=self.reject,
        ))

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        bl.setSpacing(sp.GAP_MD)

        entry      = self._snapshot.get("current_buy_price")
        cur_sl     = self._snapshot.get("stop_loss")
        cur_sl_pct = abs(float(getattr(state_manager.get_state(), "stoploss_percentage", 1.0)))

        rows = []
        if entry is not None:
            rows.append(("Entry Price", f"₹{float(entry):.2f}"))
        if cur_sl is not None:
            rows.append(("Current Stop", f"₹{float(cur_sl):.2f}", c.RED))
        rows.append(("Current SL %", f"{cur_sl_pct:.1f}%", c.RED))
        bl.addWidget(_summary_card(rows, c=c, ty=ty, sp=sp))

        bl.addWidget(_sep(c))

        bl.addWidget(_section_label("New Stop-Loss %", c=c, ty=ty))

        self._input = _input_field(
            f"e.g. {cur_sl_pct:.1f}", f"{cur_sl_pct:.1f}",
            c=c, ty=ty, sp=sp,
        )
        self._input.selectAll()
        bl.addWidget(self._input)

        self._preview = _preview_lbl(c.RED, c=c, ty=ty)
        bl.addWidget(self._preview)
        self._input.textChanged.connect(self._update_preview)
        self._update_preview(self._input.text())

        bl.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)
        cancel_btn      = create_modern_button("Cancel")
        self._apply_btn = create_modern_button("Apply", primary=True, icon="✓")
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._apply_btn)
        bl.addLayout(btn_row)

        ml.addWidget(body, 1)
        root.addWidget(self.main_card)

    def _update_preview(self, text: str):
        try:
            pct   = float(text)
            entry = self._snapshot.get("current_buy_price")
            if entry and pct > 0:
                sl = float(entry) * (1 - pct / 100)
                self._preview.setText(f"→ New SL trigger: ₹{sl:.2f}")
                self._preview.setStyleSheet(
                    f"color: {self._c.RED}; font-size: {self._ty.SIZE_SM}pt; "
                    f"font-weight: bold; background: transparent; border: none;"
                )
            else:
                self._preview.setText("")
        except (ValueError, TypeError):
            self._preview.setText("")

    def _on_apply(self):
        try:
            pct = float(self._input.text())
            if pct <= 0:
                self._show_error("SL % must be greater than 0")
                return
            state = state_manager.get_state()
            state.stoploss_percentage = pct
            entry = state.current_buy_price
            if entry is not None:
                state.stop_loss = float(entry) * (1 - pct / 100)
                logger.info(f"[ModifySLDialog] SL updated: {pct:.1f}% → ₹{state.stop_loss:.2f}")
            else:
                state.stop_loss = None
            self.accept()
        except (ValueError, TypeError):
            self._show_error("Please enter a valid percentage")
        except Exception as e:
            logger.error(f"[ModifySLDialog._on_apply] {e}", exc_info=True)
            self._show_error(f"Failed to update SL: {e}")

    def _show_error(self, msg: str):
        self._preview.setStyleSheet(
            f"color: {self._c.RED_BRIGHT}; font-size: {self._ty.SIZE_SM}pt; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        self._preview.setText(f"⚠  {msg}")

    def apply_theme(self, _=None):
        try:
            if hasattr(self, "main_card") and self.main_card:
                self.main_card._apply_style()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# ExitConfirmDialog
# ─────────────────────────────────────────────────────────────────────────────

class ExitConfirmDialog(ThemedDialog):
    """
    Confirmation dialog before manually exiting an open trade.

    Layout
    ──────
    Title bar  →  CONFIRM EXIT  [EX badge] [✕]
    Trade summary card  (Direction / Symbol / Entry / Current / P&L)
    Warning card  (yellow accent — "executed at market price")
    Button row  →  [Cancel (primary)]  [Confirm Exit (danger)]

    Cancel is the visually dominant button to prevent accidental exits.
    """

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="CONFIRM EXIT",
            icon="EX",
            size=(400, 530),
        )
        self._snapshot      = state_manager.get_position_snapshot()
        self._full_snapshot = state_manager.get_snapshot()
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        c, ty, sp = self._c, self._ty, self._sp

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        self.main_card = ModernCard(self, elevated=True)
        ml = QVBoxLayout(self.main_card)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        ml.addWidget(build_title_bar(
            self, "CONFIRM EXIT", icon="EX",
            on_close=self.reject,
        ))

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG)
        bl.setSpacing(sp.GAP_MD)

        # ── Trade summary card ────────────────────────────────────────────────
        snap     = self._snapshot
        full     = self._full_snapshot
        position = full.get("current_position", "—")
        symbol   = full.get("current_trading_symbol", "—")
        entry    = snap.get("current_buy_price")
        current  = snap.get("current_price")
        pnl_pct  = snap.get("percentage_change")

        pos_str   = str(position).upper() if position else "—"
        pos_color = (
            c.GREEN if "CALL" in pos_str
            else c.BLUE if "PUT" in pos_str
            else c.TEXT_MAIN
        )

        rows = [("Direction", pos_str, pos_color)]
        if symbol and str(symbol) not in ("—", "None"):
            rows.append(("Symbol", str(symbol)))
        if entry is not None:
            rows.append(("Entry Price", f"₹{float(entry):.2f}"))
        if current is not None:
            rows.append(("Current Price", f"₹{float(current):.2f}"))
        if pnl_pct is not None:
            pct_val   = float(pnl_pct)
            pct_color = c.GREEN if pct_val >= 0 else c.RED
            rows.append(("Unrealised P&L", f"{pct_val:+.2f}%", pct_color))

        bl.addWidget(_summary_card(rows, c=c, ty=ty, sp=sp))

        # ── Warning note ──────────────────────────────────────────────────────
        bl.addWidget(_warn_card(
            "Exit will be executed at market price immediately.",
            c=c, ty=ty, sp=sp,
        ))

        bl.addStretch()

        # ── Button row ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)

        cancel_btn = create_modern_button("Cancel", primary=True)
        exit_btn   = create_modern_button("Confirm Exit", danger=True, icon="🚪")
        cancel_btn.setMinimumWidth(120)
        exit_btn.setMinimumWidth(120)
        cancel_btn.clicked.connect(self.reject)
        exit_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn, 3)
        btn_row.addWidget(exit_btn,   2)
        bl.addLayout(btn_row)

        ml.addWidget(body, 1)
        root.addWidget(self.main_card)

    def apply_theme(self, _=None):
        try:
            if hasattr(self, "main_card") and self.main_card:
                self.main_card._apply_style()
        except Exception:
            pass