"""
gui/popups/modify_sl_tp_popup.py
=================================
Popups for live-trade modification: Stop-Loss, Take-Profit, and Exit confirmation.

Three dialogs, all sharing the same design language as the existing settings dialogs:
  • ModifyTPDialog   — update TP % for the current trade
  • ModifySLDialog   — update SL % for the current trade
  • ExitConfirmDialog — confirm a manual exit with trade summary
"""

import logging
import threading

from PyQt5.QtCore    import Qt, pyqtSignal, QTimer
from PyQt5.QtGui     import QDoubleValidator
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QWidget
)

from data.trade_state_manager import state_manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

class _ThemedDialog(QDialog):
    """Base dialog with theme tokens and shared styling helpers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        theme_manager.theme_changed.connect(self._apply_base_theme)
        theme_manager.density_changed.connect(self._apply_base_theme)

    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def _apply_base_theme(self, _=None):
        c, ty = self._c, self._ty
        self.setStyleSheet(f"""
            QDialog {{
                background: {c.BG_MAIN};
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
            QLineEdit {{
                background: {c.BG_INPUT};
                color: {c.TEXT_MAIN};
                border: 1px solid {c.BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: {ty.SIZE_BODY}pt;
                selection-background-color: {c.BG_SELECTED};
            }}
            QLineEdit:focus {{
                border-color: {c.BORDER_FOCUS};
            }}
        """)

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border: none; background: {self._c.BORDER}; max-height: 1px;")
        return sep

    def _make_header(self, icon: str, title: str, subtitle: str = "") -> QWidget:
        c, ty, sp = self._c, self._ty, self._sp
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, sp.GAP_SM)
        lay.setSpacing(sp.GAP_XS)

        title_lbl = QLabel(f"{icon}  {title}")
        title_lbl.setStyleSheet(
            f"color: {c.TEXT_MAIN}; font-size: {ty.SIZE_XL}pt; "
            f"font-weight: {ty.WEIGHT_HEAVY};"
        )
        lay.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(
                f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt;"
            )
            lay.addWidget(sub_lbl)

        lay.addWidget(self._make_separator())
        return w

    def _make_info_row(self, label: str, value: str, value_color: str = None) -> QWidget:
        c, ty, sp = self._c, self._ty, self._sp
        vc = value_color or c.TEXT_MAIN
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt;")
        val = QLabel(value)
        val.setStyleSheet(
            f"color: {vc}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        lay.addWidget(lbl)
        lay.addStretch()
        lay.addWidget(val)
        return w

    def _make_btn(self, text: str, primary: bool = False, danger: bool = False) -> QPushButton:
        c, ty, sp = self._c, self._ty, self._sp
        btn = QPushButton(text)
        btn.setMinimumHeight(sp.BTN_HEIGHT_SM + 6)
        btn.setMinimumWidth(100)

        if danger:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.RED};
                    color: {c.TEXT_INVERSE};
                    border: none;
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_XS}px {sp.PAD_LG}px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QPushButton:hover {{ background: {c.RED_BRIGHT}; }}
                QPushButton:pressed {{ background: {c.RED}; }}
            """)
        elif primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.BLUE};
                    color: {c.TEXT_INVERSE};
                    border: none;
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_XS}px {sp.PAD_LG}px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QPushButton:hover {{ background: {c.BORDER_FOCUS}; }}
                QPushButton:pressed {{ background: {c.BLUE}; }}
                QPushButton:disabled {{ background: {c.BG_HOVER}; color: {c.TEXT_DISABLED}; }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_MAIN};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_XS}px {sp.PAD_LG}px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QPushButton:hover {{ background: {c.BORDER}; }}
            """)
        return btn


# ─────────────────────────────────────────────────────────────────────────────
# ModifyTPDialog
# ─────────────────────────────────────────────────────────────────────────────

class ModifyTPDialog(_ThemedDialog):
    """
    Update Take-Profit % for the current open trade.

    On accept: writes new tp_percentage + recalculates tp_point in TradeState.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modify Take-Profit")
        self.setFixedWidth(360)

        self._apply_base_theme()
        self._snapshot = state_manager.get_position_snapshot()
        self._build_ui()

    def _build_ui(self):
        sp = self._sp
        c  = self._c
        ty = self._ty

        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
        root.setSpacing(sp.GAP_MD)

        # Header
        root.addWidget(self._make_header("🎯", "Modify Take-Profit", "Adjust TP % for the current trade"))

        # Current trade context
        entry  = self._snapshot.get("current_buy_price")
        cur_tp = self._snapshot.get("tp_point")
        cur_tp_pct = state_manager.get_state().tp_percentage

        if entry is not None:
            root.addWidget(self._make_info_row("Entry Price", f"₹{float(entry):.2f}"))
        if cur_tp is not None:
            root.addWidget(self._make_info_row("Current TP", f"₹{float(cur_tp):.2f}", c.GREEN))
        root.addWidget(self._make_info_row("Current TP %", f"{cur_tp_pct:.1f}%", c.GREEN))

        root.addWidget(self._make_separator())

        # Input
        input_lbl = QLabel("New Take-Profit %")
        input_lbl.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        root.addWidget(input_lbl)

        self._input = QLineEdit()
        self._input.setPlaceholderText(f"e.g. {cur_tp_pct:.1f}")
        self._input.setText(f"{cur_tp_pct:.1f}")
        self._input.setValidator(QDoubleValidator(0.1, 100.0, 2, self._input))
        self._input.selectAll()
        root.addWidget(self._input)

        # Preview label — updates as user types
        self._preview = QLabel("")
        self._preview.setStyleSheet(
            f"color: {c.GREEN}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        root.addWidget(self._preview)
        self._input.textChanged.connect(self._update_preview)
        self._update_preview(self._input.text())

        root.addSpacing(sp.GAP_SM)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)
        cancel_btn = self._make_btn("Cancel")
        self._apply_btn = self._make_btn("Apply", primary=True)
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._apply_btn)
        root.addLayout(btn_row)

    def _update_preview(self, text: str):
        try:
            pct = float(text)
            entry = self._snapshot.get("current_buy_price")
            if entry and pct > 0:
                tp = float(entry) * (1 + pct / 100)
                self._preview.setText(f"→ New TP target: ₹{tp:.2f}")
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
                logger.info(
                    f"[ModifyTPDialog] TP updated: {pct:.1f}% → ₹{state.tp_point:.2f}"
                )
            else:
                state.tp_point = None

            self.accept()

        except (ValueError, TypeError):
            self._show_error("Please enter a valid percentage")
        except Exception as e:
            logger.error(f"[ModifyTPDialog._on_apply] {e}", exc_info=True)
            self._show_error(f"Failed to update TP: {e}")

    def _show_error(self, msg: str):
        c, ty = self._c, self._ty
        self._preview.setStyleSheet(
            f"color: {c.RED}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        self._preview.setText(f"⚠ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# ModifySLDialog
# ─────────────────────────────────────────────────────────────────────────────

class ModifySLDialog(_ThemedDialog):
    """
    Update Stop-Loss % for the current open trade.

    On accept: writes new stoploss_percentage + recalculates stop_loss in TradeState.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modify Stop-Loss")
        self.setFixedWidth(360)

        self._apply_base_theme()
        self._snapshot = state_manager.get_position_snapshot()
        self._build_ui()

    def _build_ui(self):
        sp = self._sp
        c  = self._c
        ty = self._ty

        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
        root.setSpacing(sp.GAP_MD)

        # Header
        root.addWidget(self._make_header("🛑", "Modify Stop-Loss", "Adjust SL % for the current trade"))

        # Current trade context
        entry   = self._snapshot.get("current_buy_price")
        cur_sl  = self._snapshot.get("stop_loss")
        cur_sl_pct = abs(state_manager.get_state().stoploss_percentage)

        if entry is not None:
            root.addWidget(self._make_info_row("Entry Price", f"₹{float(entry):.2f}"))
        if cur_sl is not None:
            root.addWidget(self._make_info_row("Current SL", f"₹{float(cur_sl):.2f}", c.RED))
        root.addWidget(self._make_info_row("Current SL %", f"{cur_sl_pct:.1f}%", c.RED))

        root.addWidget(self._make_separator())

        # Input
        input_lbl = QLabel("New Stop-Loss %")
        input_lbl.setStyleSheet(
            f"color: {c.TEXT_DIM}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        root.addWidget(input_lbl)

        self._input = QLineEdit()
        self._input.setPlaceholderText(f"e.g. {cur_sl_pct:.1f}")
        self._input.setText(f"{cur_sl_pct:.1f}")
        self._input.setValidator(QDoubleValidator(0.1, 100.0, 2, self._input))
        self._input.selectAll()
        root.addWidget(self._input)

        self._preview = QLabel("")
        self._preview.setStyleSheet(
            f"color: {c.RED}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        root.addWidget(self._preview)
        self._input.textChanged.connect(self._update_preview)
        self._update_preview(self._input.text())

        root.addSpacing(sp.GAP_SM)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)
        cancel_btn = self._make_btn("Cancel")
        self._apply_btn = self._make_btn("Apply", primary=True)
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._apply_btn)
        root.addLayout(btn_row)

    def _update_preview(self, text: str):
        try:
            pct = float(text)
            entry = self._snapshot.get("current_buy_price")
            if entry and pct > 0:
                sl = float(entry) * (1 - pct / 100)
                self._preview.setText(f"→ New SL trigger: ₹{sl:.2f}")
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
            # stoploss_percentage is stored as a positive value in state;
            # the negative sign is applied internally when calculating the price
            state.stoploss_percentage = pct

            entry = state.current_buy_price
            if entry is not None:
                state.stop_loss = float(entry) * (1 - pct / 100)
                logger.info(
                    f"[ModifySLDialog] SL updated: {pct:.1f}% → ₹{state.stop_loss:.2f}"
                )
            else:
                state.stop_loss = None

            self.accept()

        except (ValueError, TypeError):
            self._show_error("Please enter a valid percentage")
        except Exception as e:
            logger.error(f"[ModifySLDialog._on_apply] {e}", exc_info=True)
            self._show_error(f"Failed to update SL: {e}")

    def _show_error(self, msg: str):
        c, ty = self._c, self._ty
        self._preview.setStyleSheet(
            f"color: {c.RED}; font-size: {ty.SIZE_SM}pt; font-weight: {ty.WEIGHT_BOLD};"
        )
        self._preview.setText(f"⚠ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# ExitConfirmDialog
# ─────────────────────────────────────────────────────────────────────────────

class ExitConfirmDialog(_ThemedDialog):
    """
    Confirmation dialog before manually exiting an open trade.

    Shows the current trade summary (symbol, entry, current price, P&L)
    and requires explicit confirmation before the exit is executed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Exit")
        self.setFixedWidth(380)

        self._apply_base_theme()
        self._snapshot = state_manager.get_position_snapshot()
        self._build_ui()

    def _build_ui(self):
        sp = self._sp
        c  = self._c
        ty = self._ty

        root = QVBoxLayout(self)
        root.setContentsMargins(sp.PAD_LG, sp.PAD_LG, sp.PAD_LG, sp.PAD_LG)
        root.setSpacing(sp.GAP_MD)

        # Header
        root.addWidget(self._make_header(
            "⚡", "Exit Position",
            "This will immediately close your current trade."
        ))

        # Trade summary card
        snap  = self._snapshot
        full  = state_manager.get_snapshot()

        position = full.get("current_position", "—")
        symbol   = full.get("current_trading_symbol", "—")
        entry    = snap.get("current_buy_price")
        current  = snap.get("current_price")
        pnl_pct  = snap.get("percentage_change")

        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"""
            QFrame {{
                background: {c.BG_PANEL};
                border: 1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
            }}
        """)
        sf_lay = QVBoxLayout(summary_frame)
        sf_lay.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)
        sf_lay.setSpacing(sp.GAP_XS)

        pos_color = c.GREEN if str(position).upper() == "CALL" else c.BLUE
        sf_lay.addWidget(self._make_info_row("Position", str(position), pos_color))
        sf_lay.addWidget(self._make_info_row("Symbol", str(symbol) if symbol else "—"))

        if entry is not None:
            sf_lay.addWidget(self._make_info_row("Entry Price", f"₹{float(entry):.2f}"))
        if current is not None:
            sf_lay.addWidget(self._make_info_row("Current Price", f"₹{float(current):.2f}"))
        if pnl_pct is not None:
            pct_val = float(pnl_pct)
            pct_color = c.GREEN if pct_val >= 0 else c.RED
            sf_lay.addWidget(
                self._make_info_row("Unrealized P&L", f"{pct_val:+.2f}%", pct_color)
            )

        root.addWidget(summary_frame)

        # Warning note
        warn = QLabel("⚠  Exit will be executed at market price.")
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"color: {c.YELLOW}; font-size: {ty.SIZE_XS}pt; "
            f"background: transparent; border: none;"
        )
        root.addWidget(warn)

        root.addSpacing(sp.GAP_SM)

        # Buttons — cancel is visually dominant to prevent accidental exits
        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp.GAP_SM)
        cancel_btn = self._make_btn("Cancel", primary=True)
        exit_btn   = self._make_btn("🚪  Confirm Exit", danger=True)
        cancel_btn.clicked.connect(self.reject)
        exit_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn, 2)
        btn_row.addWidget(exit_btn, 1)
        root.addLayout(btn_row)