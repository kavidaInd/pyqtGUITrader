# gui/dialog_base.py
"""
Shared base components for ALL dialogs, popups, and settings windows.

Design language (matches dynamic_signal_debug_popup + strategy_picker_sidebar):
  • Frameless + translucent outer shell — 12-20px margin gives "floating" depth
  • outerFrame / ModernCard(elevated=True):
        BG_MAIN body, 1px BORDER_STRONG sides, 2px YELLOW_BRIGHT top accent, 8px radius
  • titleBar   :  44px, BG_PANEL, monogram badge (YELLOW_BRIGHT) + CAPS title
                  + ghost icon buttons (↺ optional, ✕ close)
  • sectionHdr :  30px, BG_PANEL, accent dot + CAPS text
  • Scrollbars :  6px slim, BORDER_STRONG handle  — via make_scrollbar_ss()
  • Buttons    :  accent (YELLOW fill), primary (blue gradient), danger (red glow),
                  ghost/secondary (outlined transparent)

Architecture note
─────────────────
ThemedDialog does NOT own a root QVBoxLayout.  Every subclass dialog already
builds its own complete layout tree rooted on `self` (root = QVBoxLayout(self),
main_card = ModernCard(self, elevated=True), etc.).  ThemedDialog only:
  • Sets window flags / translucent background
  • Wires theme signals → calls apply_theme() safely AFTER subclass __init__
  • Provides drag support helpers
  • Exposes _c / _ty / _sp shortcuts via ThemedMixin

The new visual design is delivered by:
  • ModernCard(elevated=True)  →  YELLOW_BRIGHT top border (see _apply_style)
  • _create_title_bar helpers  →  monogram badge + ghost buttons
  • make_scrollbar_ss()         →  slim 6-px scrollbars everywhere
  • create_section_header()     →  accent-dot CAPS labels
  • create_modern_button()      →  full button set

Usage:
    class MyPopup(ThemedDialog):
        def __init__(self, parent=None):
            self._safe_defaults_init()
            super().__init__(parent, title="MY POPUP", icon="MP", size=(900, 650))
            # build your own root = QVBoxLayout(self) / ModernCard here
            root = QVBoxLayout(self)
            root.setContentsMargins(12, 12, 12, 12)
            card = ModernCard(self, elevated=True)
            root.addWidget(card)
            # ...
            self.apply_theme()

    def _create_title_bar(self):
        return build_title_bar(self, "MY POPUP", icon="MP",
                               on_close=self.reject)

    def apply_theme(self, _=None):
        if not self.main_card: return   # guard during early init
        self.main_card._apply_style()
        # ...
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
# ThemedMixin — shorthand theme-token properties
# ─────────────────────────────────────────────────────────────────────────────

class ThemedMixin:
    """Mix into any QWidget subclass for _c / _ty / _sp shorthand."""

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
    6-px slim scrollbar stylesheet string.
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
# ModernCard — themed card frame
# ─────────────────────────────────────────────────────────────────────────────

class ModernCard(QFrame, ThemedMixin):
    """
    Themed card frame.

    elevated=True  →  new reference design:
        BG_MAIN body, 1px BORDER_STRONG sides, 2px YELLOW_BRIGHT top, 8px radius
        (matches dynamic_signal_debug_popup / strategy_picker_sidebar outerFrame)

    elevated=False →  inner panel card:
        BG_PANEL, 1px BORDER, RADIUS_LG
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
            c = self._c
            sp = self._sp
            if self._elevated:
                self.setStyleSheet(f"""
                    QFrame#modernCard {{
                        background:    {c.BG_MAIN};
                        border:        1px solid {c.BORDER_STRONG};
                        border-top:    2px solid {c.YELLOW_BRIGHT};
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
# Title bar builder — the new design (monogram badge + ghost buttons)
# ─────────────────────────────────────────────────────────────────────────────

def build_title_bar(
        dialog,
        title: str,
        icon: str = "",
        on_close: Callable = None,
        on_refresh: Callable = None,
        accent_color: str = "YELLOW_BRIGHT",
        height: int = 44,
) -> QWidget:
    """
    Build the new-design title bar and wire drag to `dialog`.

    Parameters
    ----------
    dialog       : the QDialog / ThemedDialog instance
    title        : text shown in title bar (displayed as-is; CAPS recommended)
    icon         : short monogram text for the badge (≤3 chars, e.g. "LV")
    on_close     : slot called when ✕ is clicked  (default: dialog.reject)
    on_refresh   : if given, adds a ↺ ghost button before ✕
    accent_color : palette token name for badge + badge background
    height       : title bar height in px (default 44)

    Returns the QWidget title bar — add it to your layout with:
        main_layout.addWidget(build_title_bar(self, "MY TITLE", icon="MT"))
    """
    c = theme_manager.palette
    ty = theme_manager.typography
    acc = getattr(c, accent_color, c.YELLOW_BRIGHT)

    bar = QWidget()
    bar.setObjectName("titleBar")
    bar.setFixedHeight(height)

    lay = QHBoxLayout(bar)
    lay.setContentsMargins(14, 0, 10, 0)
    lay.setSpacing(10)

    # ── Monogram badge ────────────────────────────────────────────────────
    if icon:
        badge = QLabel(icon)
        badge.setFixedSize(28, 26)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            color:          {c.TEXT_INVERSE};
            background:     {acc};
            border-radius:  4px;
            font-size:      {ty.SIZE_XS}pt;
            font-weight:    900;
            font-family:    'Consolas', monospace;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(badge)

    # ── Title text ────────────────────────────────────────────────────────
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"""
        color:          {c.TEXT_MAIN};
        font-size:      {ty.SIZE_SM}pt;
        font-weight:    bold;
        letter-spacing: 1.8px;
        background:     transparent;
    """)
    lay.addWidget(title_lbl)
    lay.addStretch()

    # ── Ghost buttons ─────────────────────────────────────────────────────
    def _ghost_btn(text: str, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {c.TEXT_DIM};
                border: none; border-radius: 14px;
                font-size: {ty.SIZE_BODY}pt; font-weight: bold;
            }}
            QPushButton:hover {{
                background: {'#ef444433' if danger else c.BG_HOVER};
                color:      {'#f87171' if danger else c.TEXT_MAIN};
            }}
            QPushButton:pressed {{
                background: {'#ef4444' if danger else c.BG_MAIN};
                color: white;
            }}
        """)
        return btn

    if on_refresh:
        ref_btn = _ghost_btn("↺")
        ref_btn.setToolTip("Refresh")
        ref_btn.clicked.connect(on_refresh)
        lay.addWidget(ref_btn)

    close_btn = _ghost_btn("✕", danger=True)
    close_btn.setToolTip("Close")
    close_btn.clicked.connect(on_close if on_close else dialog.reject)
    lay.addWidget(close_btn)

    # ── Wire drag to dialog ───────────────────────────────────────────────
    bar.mousePressEvent = lambda e: (
        setattr(dialog, '_drag_pos',
                e.globalPos() - dialog.frameGeometry().topLeft())
        if e.button() == Qt.LeftButton else None
    )
    bar.mouseMoveEvent = lambda e: (
        dialog.move(e.globalPos() - dialog._drag_pos)
        if e.buttons() == Qt.LeftButton
           and getattr(dialog, '_drag_pos', None) is not None else None
    )
    bar.mouseReleaseEvent = lambda e: setattr(dialog, '_drag_pos', None)

    return bar


# ─────────────────────────────────────────────────────────────────────────────
# Factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def create_section_header(text: str, parent=None) -> QWidget:
    """
    30px CAPS section label with YELLOW_BRIGHT accent dot.
    Matches strategy_picker_sidebar._make_section_header().
    Returns a QWidget (not a bare QLabel).
    """
    c = theme_manager.palette
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
        text: str,
        primary: bool = False,
        icon: str = "",
        parent=None,
        danger: bool = False,
        accent: bool = False,
) -> QPushButton:
    """
    Consistent button factory.

    accent  → solid YELLOW_BRIGHT fill  (⚡ Activate style)
    primary → blue gradient fill
    danger  → red glow outline → solid red on hover
    default → ghost / outlined secondary (transparent, YELLOW_BRIGHT on hover)
    """
    c = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    label = f"{icon}  {text}" if icon else text
    btn = QPushButton(label, parent)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(34)

    if accent:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.YELLOW_BRIGHT}; color: {c.BG_MAIN};
                border: none; border-radius: {sp.RADIUS_MD}px;
                padding: 0 18px; font-size: {ty.SIZE_SM}pt; font-weight: bold;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover   {{ background: {c.ORANGE}; }}
            QPushButton:pressed {{ background: {c.YELLOW}; }}
            QPushButton:disabled {{ background: {c.BG_HOVER}; color: {c.TEXT_DISABLED}; }}
        """)
    elif danger:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.RED_BRIGHT}22; color: {c.RED_BRIGHT};
                border: 1px solid {c.RED_BRIGHT}66; border-radius: {sp.RADIUS_MD}px;
                padding: 0 14px; font-size: {ty.SIZE_SM}pt; font-weight: bold;
            }}
            QPushButton:hover   {{ background: {c.RED_BRIGHT}; color: white; }}
            QPushButton:pressed {{ background: {c.RED}; color: white; }}
            QPushButton:disabled {{ background: {c.BG_CARD}; color: {c.TEXT_DISABLED}; border-color: {c.BORDER_DIM}; }}
        """)
    elif primary:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                            stop:0 {c.BLUE}, stop:1 {c.BLUE_DARK});
                color: {c.TEXT_INVERSE}; border: none; border-radius: {sp.RADIUS_MD}px;
                padding: 0 18px; font-size: {ty.SIZE_SM}pt; font-weight: bold; min-width: 120px;
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
                background: transparent; color: {c.TEXT_DIM};
                border: 1px solid {c.BORDER}; border-radius: {sp.RADIUS_MD}px;
                padding: 0 14px; font-size: {ty.SIZE_SM}pt; font-weight: bold;
            }}
            QPushButton:hover  {{ border-color: {c.YELLOW_BRIGHT}; color: {c.YELLOW_BRIGHT}; }}
            QPushButton:pressed {{ background: {c.BG_HOVER}; }}
            QPushButton:disabled {{ color: {c.TEXT_DISABLED}; border-color: {c.BORDER_DIM}; }}
        """)
    return btn


def apply_tab_style(tab_widget, accent_color: str = "YELLOW_BRIGHT") -> None:
    """
    Unified QTabWidget stylesheet.
    accent_color is a palette token name for selected-tab underline.
    Matches dynamic_signal_debug_popup tab style.
    """
    c = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing
    acc = getattr(c, accent_color, c.YELLOW_BRIGHT)

    tab_widget.setStyleSheet(f"""
        QTabWidget::pane {{
            border: none; border-top: 1px solid {c.BORDER}; background: {c.BG_MAIN};
        }}
        QTabBar::tab {{
            background: {c.BG_PANEL}; color: {c.TEXT_DIM};
            border: none; border-right: 1px solid {c.BORDER};
            padding: {sp.PAD_SM}px {sp.PAD_XL}px;
            min-width: 110px; min-height: {sp.TAB_H}px;
            font-size: {ty.SIZE_SM}pt; font-weight: bold; letter-spacing: 0.3px;
        }}
        QTabBar::tab:selected {{
            color: {acc}; border-bottom: 2px solid {acc}; background: {c.BG_MAIN};
        }}
        QTabBar::tab:hover:!selected {{
            color: {c.TEXT_MAIN}; background: {c.BG_HOVER};
        }}
    """)


# ─────────────────────────────────────────────────────────────────────────────
# ThemedDialog — base class for ALL dialogs and popups
# ─────────────────────────────────────────────────────────────────────────────

class ThemedDialog(QDialog, ThemedMixin):
    """
    Lightweight base class.  Does NOT own a root layout or skeleton.

    Responsibilities:
      • Window flags (FramelessWindowHint + WA_TranslucentBackground)
      • Theme signal wiring → apply_theme() called safely after subclass init
      • Drag position state (_drag_pos)
      • _c / _ty / _sp shortcuts (via ThemedMixin)

    Each subclass builds its own complete layout tree:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        card = ModernCard(self, elevated=True)       # YELLOW_BRIGHT top border
        card_lay = QVBoxLayout(card)
        card_lay.addWidget(build_title_bar(self, "TITLE", icon="TT"))
        ...
        root.addWidget(card)
        self.apply_theme()   # call at the END of subclass __init__

    apply_theme() is NOT called during super().__init__() — subclass calls it.
    """

    def __init__(
            self,
            parent=None,
            title: str = "",
            icon: str = "",
            size: Tuple[int, int] = (800, 600),
            modal: bool = True,
            accent_color: str = "YELLOW_BRIGHT",
    ):
        super().__init__(parent)

        self._drag_pos: Optional[QPoint] = None
        self._dialog_title: str = title
        self._dialog_icon: str = icon
        self._accent_color: str = accent_color

        self.setModal(modal)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if size:
            self.setMinimumSize(*size)
            self.resize(*size)

        # Wire theme signals — apply_theme() is the subclass hook
        try:
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)
        except Exception:
            pass

        # NOTE: apply_theme() is intentionally NOT called here.
        # Subclasses must call self.apply_theme() at the end of their own __init__.

    # ── theme hook ────────────────────────────────────────────────────────────

    def apply_theme(self, _=None):
        """
        Override in subclasses to re-apply styles when the theme changes.
        Always guard with None-checks on widgets that may not exist yet:

            def apply_theme(self, _=None):
                if not self.main_card:
                    return
                self.main_card._apply_style()
                ...
        """
        pass

    # ── drag support ──────────────────────────────────────────────────────────

    def _on_drag_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def _on_drag_move(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)

    def _on_drag_release(self, event):
        self._drag_pos = None

    # ── convenience helpers ───────────────────────────────────────────────────

    def build_title_bar(
            self,
            title: str = "",
            icon: str = "",
            on_close: Callable = None,
            on_refresh: Callable = None,
            accent_color: str = "YELLOW_BRIGHT",
            height: int = 44,
    ) -> QWidget:
        """Instance method wrapper around the module-level build_title_bar()."""
        return build_title_bar(
            self,
            title=title or self._dialog_title,
            icon=icon or self._dialog_icon,
            on_close=on_close,
            on_refresh=on_refresh,
            accent_color=accent_color or self._accent_color,
            height=height,
        )
