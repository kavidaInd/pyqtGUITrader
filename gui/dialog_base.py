# gui/dialog_base.py
"""
Shared base components for all dialogs, popups, and settings windows.

Provides:
  ThemedMixin        — shorthand _c / _ty / _sp properties
  ModernCard         — themed card frame
  ThemedDialog       — QDialog base with title bar, drag support, theme wiring
  create_section_header  — small in-content section labels (NOT a duplicate title)
  create_modern_button   — consistent primary / secondary button factory

Usage:
    from gui.dialog_base import ThemedDialog, ThemedMixin, ModernCard, \
                               create_section_header, create_modern_button

    class MyPopup(ThemedDialog):
        def __init__(self, parent=None):
            super().__init__(parent, title="My Window", icon="📊", size=(800, 600))
            # add_content_widget / content_layout are ready to use
"""

import logging
from typing import Optional, Tuple

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ThemedMixin
# ─────────────────────────────────────────────────────────────────────────────

class ThemedMixin:
    """Shorthand properties for theme tokens. Mix into any QWidget subclass."""

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
# ModernCard
# ─────────────────────────────────────────────────────────────────────────────

class ModernCard(QFrame, ThemedMixin):
    """
    Themed card frame — the primary container surface for dialog content.

    elevated=True adds a gradient background for the outermost card.
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
                        background: qlineargradient(
                            x1:0, y1:0, x2:0, y2:1,
                            stop:0 {c.BG_CARD}, stop:1 {c.BG_PANEL}
                        );
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_XL}px;
                    }}
                """)
            else:
                self.setStyleSheet(f"""
                    QFrame#modernCard {{
                        background: {c.BG_PANEL};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
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

def create_section_header(text: str, parent=None) -> QLabel:
    """
    Small uppercase section label for use INSIDE content areas.
    NOT the dialog title — use ThemedDialog's built-in title bar for that.

    Example:
        layout.addWidget(create_section_header("Risk Parameters"))
    """
    c  = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    lbl = QLabel(text, parent)
    lbl.setObjectName("sectionHeader")
    lbl.setStyleSheet(f"""
        QLabel#sectionHeader {{
            color:           {c.TEXT_DIM};
            font-size:       {ty.SIZE_XS}pt;
            font-weight:     {ty.WEIGHT_BOLD};
            letter-spacing:  {ty.LETTER_CAPS};
            text-transform:  uppercase;
            padding-bottom:  {sp.PAD_SM}px;
            border-bottom:   1px solid {c.BORDER_DIM};
            margin-bottom:   {sp.PAD_SM}px;
            background:      transparent;
        }}
    """)
    return lbl


def create_modern_button(
    text: str,
    primary: bool = False,
    icon: str = "",
    parent=None,
    danger: bool = False,
) -> QPushButton:
    """
    Create a consistently styled button.

    primary=True  → filled blue action button
    danger=True   → filled red destructive button
    default       → outlined secondary button
    """
    c  = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    label = f"{icon}  {text}" if icon else text
    btn = QPushButton(label, parent)
    btn.setCursor(Qt.PointingHandCursor)

    if danger:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    {c.RED};
                color:         {c.TEXT_INVERSE};
                border:        none;
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_XL}px;
                font-size:     {ty.SIZE_BODY}pt;
                font-weight:   {ty.WEIGHT_BOLD};
                min-width:     100px;
                min-height:    {sp.BTN_HEIGHT_MD}px;
            }}
            QPushButton:hover   {{ background: {c.RED_BRIGHT}; }}
            QPushButton:pressed {{ background: {c.RED}; }}
            QPushButton:disabled {{
                background: {c.BG_CARD};
                color:      {c.TEXT_DISABLED};
            }}
        """)
    elif primary:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    qlineargradient(x1:0, y1:0, x2:0, y2:1,
                               stop:0 {c.BLUE}, stop:1 {c.BLUE_DARK});
                color:         {c.TEXT_INVERSE};
                border:        none;
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_XL}px;
                font-size:     {ty.SIZE_BODY}pt;
                font-weight:   {ty.WEIGHT_BOLD};
                min-width:     140px;
                min-height:    {sp.BTN_HEIGHT_MD}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {c.BLUE_BRIGHT}, stop:1 {c.BLUE});
            }}
            QPushButton:pressed {{ background: {c.BLUE_DARK}; }}
            QPushButton:disabled {{
                background: {c.BG_CARD};
                color:      {c.TEXT_DISABLED};
            }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background:    {c.BG_CARD};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_XL}px;
                font-size:     {ty.SIZE_BODY}pt;
                font-weight:   {ty.WEIGHT_SEMIBOLD};
                min-width:     100px;
                min-height:    {sp.BTN_HEIGHT_MD}px;
            }}
            QPushButton:hover {{
                background:   {c.BG_HOVER};
                border-color: {c.BORDER_STRONG};
                color:        {c.TEXT_BRIGHT};
            }}
            QPushButton:pressed {{ background: {c.BG_MAIN}; }}
            QPushButton:disabled {{
                color:        {c.TEXT_DISABLED};
                border-color: {c.BORDER_DIM};
            }}
        """)

    return btn


def apply_tab_style(tab_widget) -> None:
    """
    Apply the unified tab style to any QTabWidget.
    Call this once after creating the tab widget.
    """
    c  = theme_manager.palette
    ty = theme_manager.typography
    sp = theme_manager.spacing

    tab_widget.setStyleSheet(f"""
        QTabWidget::pane {{
            border:        {sp.SEPARATOR}px solid {c.BORDER};
            border-radius: 0 0 {sp.RADIUS_MD}px {sp.RADIUS_MD}px;
            background:    {c.BG_MAIN};
            top:           -1px;
        }}
        QTabBar {{
            border: none;
            background: transparent;
        }}
        QTabBar::tab {{
            background:    {c.BG_CARD};
            color:         {c.TEXT_DIM};
            padding:       {sp.PAD_SM}px {sp.PAD_LG}px;
            border:        {sp.SEPARATOR}px solid {c.BORDER};
            border-bottom: none;
            border-radius: {sp.RADIUS_MD}px {sp.RADIUS_MD}px 0 0;
            min-width:     110px;
            font-size:     {ty.SIZE_SM}pt;
            font-weight:   {ty.WEIGHT_SEMIBOLD};
            min-height:    {sp.TAB_H}px;
            margin-right:  2px;
        }}
        QTabBar::tab:selected {{
            background:    {c.BG_MAIN};
            color:         {c.TEXT_BRIGHT};
            border-color:  {c.BORDER};
            border-bottom: 2px solid {c.BLUE};
            font-weight:   {ty.WEIGHT_BOLD};
        }}
        QTabBar::tab:hover:!selected {{
            background: {c.BG_HOVER};
            color:      {c.TEXT_MAIN};
        }}
    """)


# ─────────────────────────────────────────────────────────────────────────────
# ThemedDialog — base class for ALL dialogs and popups
# ─────────────────────────────────────────────────────────────────────────────

class ThemedDialog(QDialog, ThemedMixin):
    """
    Base class for all frameless themed dialogs.

    Features:
    • Single title bar (no duplicate ModernHeader inside content)
    • Draggable window via title bar
    • Theme / density signals wired automatically
    • content_layout ready for subclass content
    • Consistent outer card with rounded corners

    Subclass usage:
        class MyDialog(ThemedDialog):
            def __init__(self, parent=None):
                super().__init__(parent,
                    title="My Dialog",
                    icon="⚙️",
                    size=(800, 600))
                self._build_content()

            def _build_content(self):
                # Use self.content_layout
                self.content_layout.addWidget(...)
    """

    def __init__(
        self,
        parent=None,
        title: str = "",
        icon: str = "",
        size: Tuple[int, int] = (700, 550),
        modal: bool = True,
    ):
        super().__init__(parent)
        self._drag_pos: Optional[QPoint] = None

        self.setModal(modal)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(*size)
        self.resize(*size)

        # Wire theme signals
        theme_manager.theme_changed.connect(self._on_theme_changed)
        theme_manager.density_changed.connect(self._on_theme_changed)

        # Build structural skeleton
        self._title_text = f"{icon}  {title}" if icon else title
        self._build_skeleton()
        self._on_theme_changed()

    # ── skeleton ──────────────────────────────────────────────────────────────

    def _build_skeleton(self):
        """Build outer card + title bar + content area. Called once."""
        c  = self._c
        sp = self._sp

        # Outer margin layout (gives visual "shadow" space)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        # Main card
        self.main_card = ModernCard(self, elevated=True)
        root.addWidget(self.main_card)

        card_layout = QVBoxLayout(self.main_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Title bar
        self._title_bar = self._build_title_bar()
        card_layout.addWidget(self._title_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {c.BORDER_DIM}; border: none;")
        card_layout.addWidget(sep)
        self._sep = sep

        # Content container — subclasses add their widgets here
        self._content_container = QWidget()
        self.content_layout = QVBoxLayout(self._content_container)
        self.content_layout.setContentsMargins(
            sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG
        )
        self.content_layout.setSpacing(sp.GAP_LG)
        card_layout.addWidget(self._content_container, 1)

    def _build_title_bar(self) -> QWidget:
        c  = self._c
        ty = self._ty
        sp = self._sp

        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setObjectName("dialogTitleBar")
        bar.setStyleSheet(f"""
            QWidget#dialogTitleBar {{
                background: {c.BG_CARD};
                border-radius: {sp.RADIUS_XL}px {sp.RADIUS_XL}px 0 0;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(sp.PAD_LG, 0, sp.PAD_MD, 0)
        layout.setSpacing(sp.GAP_SM)

        # Blue accent line on left
        accent = QFrame()
        accent.setFixedSize(3, 22)
        accent.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {c.BLUE_BRIGHT}, stop:1 {c.BLUE_DARK});
            border-radius: 2px;
        """)
        layout.addWidget(accent)

        layout.addSpacing(4)

        # Title label
        self._title_label = QLabel(self._title_text)
        self._title_label.setStyleSheet(f"""
            color:       {c.TEXT_BRIGHT};
            font-size:   {ty.SIZE_LG}pt;
            font-weight: {ty.WEIGHT_BOLD};
            background:  transparent;
            border:      none;
        """)
        layout.addWidget(self._title_label)
        layout.addStretch()

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background:    {c.BG_HOVER};
                color:         {c.TEXT_DIM};
                border:        none;
                border-radius: {sp.RADIUS_SM}px;
                font-size:     {ty.SIZE_MD}pt;
                font-weight:   {ty.WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background: {c.RED};
                color:      white;
            }}
            QPushButton:pressed {{
                background: {c.RED_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        # Make title bar draggable
        bar.mousePressEvent   = self._on_drag_press
        bar.mouseMoveEvent    = self._on_drag_move
        bar.mouseReleaseEvent = self._on_drag_release

        self._close_btn = close_btn
        return bar

    # ── theme ─────────────────────────────────────────────────────────────────

    def _on_theme_changed(self, _=None):
        try:
            c  = self._c
            ty = self._ty
            sp = self._sp

            # Outer dialog background (transparent to show card radius)
            self.setStyleSheet("background: transparent;")

            # Title bar
            self._title_bar.setStyleSheet(f"""
                QWidget#dialogTitleBar {{
                    background: {c.BG_CARD};
                    border-radius: {sp.RADIUS_XL}px {sp.RADIUS_XL}px 0 0;
                }}
            """)

            self._title_label.setStyleSheet(f"""
                color:       {c.TEXT_BRIGHT};
                font-size:   {ty.SIZE_LG}pt;
                font-weight: {ty.WEIGHT_BOLD};
                background:  transparent;
                border:      none;
            """)

            self._close_btn.setStyleSheet(f"""
                QPushButton {{
                    background:    {c.BG_HOVER};
                    color:         {c.TEXT_DIM};
                    border:        none;
                    border-radius: {sp.RADIUS_SM}px;
                    font-size:     {ty.SIZE_MD}pt;
                    font-weight:   {ty.WEIGHT_BOLD};
                }}
                QPushButton:hover {{
                    background: {c.RED};
                    color:      white;
                }}
            """)

            self._sep.setStyleSheet(f"background: {c.BORDER_DIM}; border: none;")

            # Content container margins
            m = self.content_layout.contentsMargins()
            self.content_layout.setContentsMargins(
                sp.PAD_XL, sp.PAD_LG, sp.PAD_XL, sp.PAD_LG
            )
            self.content_layout.setSpacing(sp.GAP_LG)

            # Let subclasses react
            self.apply_theme()

        except Exception as e:
            logger.debug(f"[ThemedDialog._on_theme_changed] {e}")

    def apply_theme(self, _=None):
        """Override in subclasses to re-apply widget-specific styles."""
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

    # ── helpers for subclasses ────────────────────────────────────────────────

    def add_content_widget(self, widget, stretch: int = 0):
        """Convenience method to add a widget to the content area."""
        self.content_layout.addWidget(widget, stretch)

    def add_content_layout(self, layout):
        """Convenience method to add a layout to the content area."""
        self.content_layout.addLayout(layout)

    def add_content_stretch(self):
        self.content_layout.addStretch()