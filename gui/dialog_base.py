# gui/dialog_base.py
"""
Shared base components for ALL dialogs, popups, and settings windows.

Design language (matches dynamic_signal_debug_popup + strategy_picker_sidebar):
  • Frameless + translucent outer shell — 12px margin gives "floating" depth
  • outerFrame  :  BG_MAIN body, 1px BORDER_STRONG sides, 2px YELLOW_BRIGHT top accent,
                   8px radius — identical to both reference files
  • titleBar    :  44px, BG_PANEL, monogram badge (YELLOW_BRIGHT) + spaced CAPS title
                   + icon-only ghost buttons (↺ refresh optional, ✕ close)
  • Content area:  BG_MAIN, subclass fills self.content_layout
  • footer      :  48px, BG_PANEL, border-top BORDER, bottom radius
  • Scrollbars  :  6px slim, BORDER_STRONG handle — baked into make_scrollbar_ss()

Public API (fully backward-compatible):
  ThemedDialog            — QDialog base; inherit and call super().__init__()
  ThemedMixin             — _c / _ty / _sp shorthand for any QWidget
  ModernCard              — themed card frame
  make_separator()        — 1px HLine / VLine QFrame
  make_scrollbar_ss()     — shared slim scrollbar stylesheet string
  create_section_header() — CAPS section label with accent dot
  create_modern_button()  — primary / secondary / danger / accent button factory
  apply_tab_style()       — unified QTabWidget stylesheet

New ThemedDialog constructor kwargs:
  title        str   window title (displayed in CAPS)
  icon         str   monogram text shown in badge (≤3 chars recommended)
  size         tuple (w, h)
  modal        bool
  accent_color str   palette token name for top-border + badge colour
                     default: "YELLOW_BRIGHT"

Subclass pattern:
    class MyPopup(ThemedDialog):
        def __init__(self, parent=None):
            super().__init__(parent,
                title="MY POPUP",
                icon="MP",
                size=(900, 650))
            self.content_layout.addWidget(my_widget)
            self.set_footer_widgets(left=[status_lbl], right=[cancel_btn, save_btn])
            self.add_title_refresh_btn(self._do_refresh)   # optional

    def apply_theme(self, _=None):   # optional override
        # re-style subclass-specific widgets on theme change
        ...
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ThemedMixin
# ─────────────────────────────────────────────────────────────────────────────

class ThemedMixin:
    """Shorthand theme-token properties.  Mix into any QWidget subclass."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


# ─────────────────────────────────────────────────────────────────────────────
# Shared stylesheet helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_scrollbar_ss() -> str:
    """
    6-px slim scrollbar stylesheet.
    Paste into any QScrollArea / QListWidget / QTextEdit stylesheet.
    Matches dynamic_signal_debug_popup and strategy_picker_sidebar exactly.
    """
    c = theme_manager.palette
    return f"""
        QScrollBar:vertical {{
            background: {c.BG_PANEL}; width: 6px; border-radius: 3px;
            margin: 0; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {c.BORDER_STRONG}; border-radius: 3px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c.TEXT_DISABLED}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical,  QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{
            background: {c.BG_PANEL}; height: 6px; border-radius: 3px;
            margin: 0; border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {c.BORDER_STRONG}; border-radius: 3px; min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {c.TEXT_DISABLED}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    """


def make_separator(parent=None, vertical: bool = False) -> QFrame:
    """Return a 1-px themed separator line (horizontal by default)."""
    sep = QFrame(parent)
    if vertical:
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
    else:
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
    sep.setStyleSheet(
        f"background: {theme_manager.palette.BORDER}; border: none;"
    )
    return sep


# ─────────────────────────────────────────────────────────────────────────────
# ModernCard  (kept for backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

class ModernCard(QFrame, ThemedMixin):
    """
    Themed card frame.  elevated=True renders the full "floating window" style
    (1px BORDER_STRONG sides, 2px YELLOW_BRIGHT top, 8px radius) matching the
    reference popups.  elevated=False is a simple inner-panel card.
    """

    def __init__(self, parent=None, elevated: bool = False):
        super().__init__(parent)
        self.setObjectName("modernCard")
        self._elevated = elevated
        self._apply_style()
        theme_manager.theme_changed.connect(self._apply_style)
        theme_manager.density_changed.connect(self._apply_style)

    def _apply_style(self, _=None):
        try:
            c  = self._c
            sp = self._sp
            if self._elevated:
                self.setStyleSheet(f"""
                    QFrame#modernCard {{
                        background: {c.BG_MAIN};
                        border:     1px solid {c.BORDER_STRONG};
                        border-top: 2px solid {c.YELLOW_BRIGHT};
                        border-radius: 8px;
                    }}
                """)
            else:
                self.setStyleSheet(f"""
                    QFrame#modernCard {{
                        background:    {c.BG_PANEL};
                        border:        1px solid {c.BORDER};
                        border-radius: {sp.RADIUS_LG}px;
                    }}
                    QFrame#modernCard:hover {{
                        border-color: {c.BORDER_STRONG};
                    }}
                """)
        except Exception as e:
            logger.debug(f"[ModernCard._apply_style] {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def create_section_header(text: str, parent=None) -> QWidget:
    """
    Small CAPS section label with a YELLOW_BRIGHT accent dot.
    Returns a 30px-tall QWidget (not a bare QLabel).
    Matches strategy_picker_sidebar._make_section_header().
    """
    c  = theme_manager.palette
    ty = theme_manager.typography

    wrapper = QWidget(parent)
    wrapper.setObjectName("sectionHdr")
    wrapper.setFixedHeight(30)

    lay = QHBoxLayout(wrapper)
    lay.setContentsMargins(14, 0, 14, 0)
    lay.setSpacing(8)

    dot = QFrame()
    dot.setFixedSize(5, 5)
    dot.setStyleSheet(
        f"background: {c.YELLOW_BRIGHT}; border-radius: 3px; border: none;"
    )
    lay.addWidget(dot)

    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        color:           {c.TEXT_DISABLED};
        font-size:       {ty.SIZE_XS}pt;
        font-weight:     bold;
        letter-spacing:  1.0px;
        background:      transparent;
    """)
    lay.addWidget(lbl)
    lay.addStretch()

    wrapper.setStyleSheet(f"""
        QWidget#sectionHdr {{
            background:    {c.BG_PANEL};
            border-bottom: 1px solid {c.BORDER};
            border-top:    1px solid {c.BORDER};
        }}
    """)
    return wrapper


def create_modern_button(
    text:    str,
    primary: bool = False,
    icon:    str  = "",
    parent         = None,
    danger:  bool = False,
    accent:  bool = False,
) -> QPushButton:
    """
    Consistent button factory.

    accent  → solid YELLOW_BRIGHT fill  (like "⚡ Activate" in strategy_picker_sidebar)
    primary → blue gradient fill
    danger  → red outline → solid red on hover  (like "✕ Close" footer buttons)
    default → ghost / outlined secondary         (like "Open Editor")
    """
    c  = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    label = f"{icon}  {text}" if icon else text
    btn = QPushButton(label, parent)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(34)

    if accent:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:     {c.YELLOW_BRIGHT};
                color:          {c.BG_MAIN};
                border:         none;
                border-radius:  {sp.RADIUS_MD}px;
                padding:        0 18px;
                font-size:      {ty.SIZE_SM}pt;
                font-weight:    bold;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover   {{ background: {c.ORANGE}; }}
            QPushButton:pressed {{ background: {c.YELLOW}; }}
            QPushButton:disabled {{ background: {c.BG_HOVER}; color: {c.TEXT_DISABLED}; }}
        """)
    elif danger:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    {c.RED_BRIGHT}22;
                color:         {c.RED_BRIGHT};
                border:        1px solid {c.RED_BRIGHT}66;
                border-radius: {sp.RADIUS_MD}px;
                padding:       0 14px;
                font-size:     {ty.SIZE_SM}pt;
                font-weight:   bold;
            }}
            QPushButton:hover   {{ background: {c.RED_BRIGHT}; color: white; }}
            QPushButton:pressed {{ background: {c.RED}; color: white; }}
            QPushButton:disabled {{ background: {c.BG_CARD}; color: {c.TEXT_DISABLED}; border-color: {c.BORDER_DIM}; }}
        """)
    elif primary:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    qlineargradient(x1:0,y1:0,x2:0,y2:1,
                               stop:0 {c.BLUE}, stop:1 {c.BLUE_DARK});
                color:         {c.TEXT_INVERSE};
                border:        none;
                border-radius: {sp.RADIUS_MD}px;
                padding:       0 18px;
                font-size:     {ty.SIZE_SM}pt;
                font-weight:   bold;
                min-width:     120px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                            stop:0 {c.BLUE_BRIGHT}, stop:1 {c.BLUE});
            }}
            QPushButton:pressed  {{ background: {c.BLUE_DARK}; }}
            QPushButton:disabled {{ background: {c.BG_CARD}; color: {c.TEXT_DISABLED}; }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    transparent;
                color:         {c.TEXT_DIM};
                border:        1px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       0 14px;
                font-size:     {ty.SIZE_SM}pt;
                font-weight:   bold;
            }}
            QPushButton:hover {{
                border-color: {c.YELLOW_BRIGHT};
                color:        {c.YELLOW_BRIGHT};
            }}
            QPushButton:pressed  {{ background: {c.BG_HOVER}; }}
            QPushButton:disabled {{ color: {c.TEXT_DISABLED}; border-color: {c.BORDER_DIM}; }}
        """)
    return btn


def apply_tab_style(tab_widget, accent_color: str = "YELLOW_BRIGHT") -> None:
    """
    Unified QTabWidget stylesheet.
    accent_color is a palette token name for selected-tab underline + text.
    Matches the tab style from dynamic_signal_debug_popup.
    """
    c   = theme_manager.palette
    ty  = theme_manager.typography
    sp  = theme_manager.spacing
    acc = getattr(c, accent_color, c.YELLOW_BRIGHT)

    tab_widget.setStyleSheet(f"""
        QTabWidget::pane {{
            border:     none;
            border-top: 1px solid {c.BORDER};
            background: {c.BG_MAIN};
        }}
        QTabBar::tab {{
            background:     {c.BG_PANEL};
            color:          {c.TEXT_DIM};
            border:         none;
            border-right:   1px solid {c.BORDER};
            padding:        {sp.PAD_SM}px {sp.PAD_XL}px;
            min-width:      110px;
            min-height:     {sp.TAB_H}px;
            font-size:      {ty.SIZE_SM}pt;
            font-weight:    bold;
            letter-spacing: 0.3px;
        }}
        QTabBar::tab:selected {{
            color:          {acc};
            border-bottom:  2px solid {acc};
            background:     {c.BG_MAIN};
        }}
        QTabBar::tab:hover:!selected {{
            color:      {c.TEXT_MAIN};
            background: {c.BG_HOVER};
        }}
    """)


# ─────────────────────────────────────────────────────────────────────────────
# ThemedDialog — base class for ALL dialogs and popups
# ─────────────────────────────────────────────────────────────────────────────

class ThemedDialog(QDialog, ThemedMixin):
    """
    Base class for all frameless themed dialogs/popups.

    See module docstring for design language and subclass usage.
    """

    def __init__(
        self,
        parent       = None,
        title:        str            = "",
        icon:         str            = "",
        size:         Tuple[int,int] = (800, 600),
        modal:        bool           = True,
        accent_color: str            = "YELLOW_BRIGHT",
    ):
        super().__init__(parent)

        # Structural state
        self._drag_pos:    Optional[QPoint]    = None
        self._title_text:  str  = title
        self._icon_text:   str  = icon
        self._accent_color:str  = accent_color

        # Refs built during _build_skeleton — safe-init for apply_theme safety
        self._outer:              Optional[QFrame]      = None
        self._title_bar:          Optional[QWidget]     = None
        self._title_label:        Optional[QLabel]      = None
        self._badge_label:        Optional[QLabel]      = None
        self._close_btn:          Optional[QPushButton] = None
        self._top_sep:            Optional[QFrame]      = None
        self._footer:             Optional[QWidget]     = None
        self._footer_left:        Optional[QHBoxLayout] = None
        self._footer_right:       Optional[QHBoxLayout] = None
        self._title_bar_btn_lay:  Optional[QHBoxLayout] = None
        self.content_layout:      Optional[QVBoxLayout] = None

        self.setModal(modal)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(*size)
        self.resize(*size)

        try:
            theme_manager.theme_changed.connect(self._on_theme_changed)
            theme_manager.density_changed.connect(self._on_theme_changed)
        except Exception:
            pass

        self._build_skeleton()
        self._on_theme_changed()

    # ── skeleton ──────────────────────────────────────────────────────────────

    def _build_skeleton(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        self._outer = QFrame()
        self._outer.setObjectName("outerFrame")

        ol = QVBoxLayout(self._outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)

        # Title bar
        self._title_bar = self._build_title_bar()
        ol.addWidget(self._title_bar)

        # Title → content separator
        self._top_sep = QFrame()
        self._top_sep.setFrameShape(QFrame.HLine)
        self._top_sep.setFixedHeight(1)
        ol.addWidget(self._top_sep)

        # Content area
        self._content_widget = QWidget()
        self._content_widget.setObjectName("contentArea")
        self.content_layout = QVBoxLayout(self._content_widget)
        sp = self._sp
        self.content_layout.setContentsMargins(
            sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG
        )
        self.content_layout.setSpacing(sp.GAP_LG)
        ol.addWidget(self._content_widget, 1)

        # Footer
        self._footer = self._build_footer()
        ol.addWidget(self._footer)

        root.addWidget(self._outer)

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(10)
        self._title_bar_btn_lay = lay

        # Monogram badge
        self._badge_label = QLabel(self._icon_text or "◈")
        self._badge_label.setFixedSize(28, 26)
        self._badge_label.setAlignment(Qt.AlignCenter)
        self._badge_label.setObjectName("monogramBadge")
        lay.addWidget(self._badge_label)

        # Title
        self._title_label = QLabel(self._title_text.upper() if self._title_text else "")
        self._title_label.setObjectName("dialogTitle")
        lay.addWidget(self._title_label)
        lay.addStretch()

        # Close button (always rightmost)
        self._close_btn = self._make_icon_btn("✕", danger=True)
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self.reject)
        lay.addWidget(self._close_btn)

        bar.mousePressEvent   = self._on_drag_press
        bar.mouseMoveEvent    = self._on_drag_move
        bar.mouseReleaseEvent = self._on_drag_release
        return bar

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        footer.setFixedHeight(48)

        lay = QHBoxLayout(footer)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        self._footer_left = QHBoxLayout()
        self._footer_left.setSpacing(8)
        lay.addLayout(self._footer_left)
        lay.addStretch()
        self._footer_right = QHBoxLayout()
        self._footer_right.setSpacing(8)
        lay.addLayout(self._footer_right)

        return footer

    # ── public helpers ────────────────────────────────────────────────────────

    def add_title_refresh_btn(self, slot: Callable) -> QPushButton:
        """Insert a ↺ ghost button in the title bar just before the close button."""
        btn = self._make_icon_btn("↺")
        btn.setToolTip("Refresh")
        btn.clicked.connect(slot)
        lay = self._title_bar_btn_lay
        # Insert before close btn (always last item)
        lay.insertWidget(lay.count() - 1, btn)
        return btn

    def set_footer_widgets(
        self,
        left:  List[QWidget] = (),
        right: List[QWidget] = (),
    ):
        """Populate footer. left→status/ghost; right→primary/danger actions."""
        for w in left:
            self._footer_left.addWidget(w)
        for w in right:
            self._footer_right.addWidget(w)

    def add_content_widget(self, widget, stretch: int = 0):
        self.content_layout.addWidget(widget, stretch)

    def add_content_layout(self, layout):
        self.content_layout.addLayout(layout)

    def add_content_stretch(self):
        self.content_layout.addStretch()

    def _make_icon_btn(self, text: str, danger: bool = False) -> QPushButton:
        """Circular 28×28 ghost button for the title bar."""
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        c  = self._c
        ty = self._ty
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    transparent;
                color:         {c.TEXT_DIM};
                border:        none;
                border-radius: 14px;
                font-size:     {ty.SIZE_BODY}pt;
                font-weight:   bold;
            }}
            QPushButton:hover {{
                background: {'#ef444433' if danger else c.BG_HOVER};
                color:      {'#f87171'   if danger else c.TEXT_MAIN};
            }}
            QPushButton:pressed {{
                background: {'#ef4444' if danger else c.BG_MAIN};
                color: white;
            }}
        """)
        return btn

    # ── theme ─────────────────────────────────────────────────────────────────

    def _on_theme_changed(self, _=None):
        try:
            c   = self._c
            ty  = self._ty
            sp  = self._sp
            acc = getattr(c, self._accent_color, c.YELLOW_BRIGHT)

            self.setStyleSheet("background: transparent;")

            if self._outer:
                self._outer.setStyleSheet(f"""
                    QFrame#outerFrame {{
                        background:    {c.BG_MAIN};
                        border:        1px solid {c.BORDER_STRONG};
                        border-top:    2px solid {acc};
                        border-radius: 8px;
                    }}
                    QWidget#titleBar {{
                        background:              {c.BG_PANEL};
                        border-top-left-radius:  8px;
                        border-top-right-radius: 8px;
                        border-bottom:           1px solid {c.BORDER};
                    }}
                    QWidget#contentArea {{
                        background: {c.BG_MAIN};
                    }}
                    QWidget#footer {{
                        background:                 {c.BG_PANEL};
                        border-top:                 1px solid {c.BORDER};
                        border-bottom-left-radius:  8px;
                        border-bottom-right-radius: 8px;
                    }}
                """)

            if self._badge_label:
                self._badge_label.setStyleSheet(f"""
                    QLabel#monogramBadge {{
                        color:          {c.TEXT_INVERSE};
                        background:     {acc};
                        border-radius:  4px;
                        font-size:      {ty.SIZE_XS}pt;
                        font-weight:    900;
                        font-family:    'Consolas', monospace;
                        letter-spacing: 0.5px;
                    }}
                """)

            if self._title_label:
                self._title_label.setStyleSheet(f"""
                    QLabel#dialogTitle {{
                        color:          {c.TEXT_MAIN};
                        font-size:      {ty.SIZE_SM}pt;
                        font-weight:    bold;
                        letter-spacing: 1.8px;
                        background:     transparent;
                    }}
                """)

            if self._close_btn:
                self._close_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; color: {c.TEXT_DIM};
                        border: none; border-radius: 14px;
                        font-size: {ty.SIZE_BODY}pt; font-weight: bold;
                    }}
                    QPushButton:hover   {{ background: #ef444433; color: #f87171; }}
                    QPushButton:pressed {{ background: #ef4444;   color: white;   }}
                """)

            if self._top_sep:
                self._top_sep.setStyleSheet(
                    f"background: {c.BORDER}; border: none;"
                )

            if self.content_layout:
                self.content_layout.setContentsMargins(
                    sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG
                )
                self.content_layout.setSpacing(sp.GAP_LG)

            self.apply_theme()

        except Exception as e:
            logger.debug(f"[ThemedDialog._on_theme_changed] {e}")

    def apply_theme(self, _=None):
        """Override in subclasses to re-apply widget-specific styles."""
        pass

    # ── drag ──────────────────────────────────────────────────────────────────

    def _on_drag_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def _on_drag_move(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)

    def _on_drag_release(self, event):
        self._drag_pos = None