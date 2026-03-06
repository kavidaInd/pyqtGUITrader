# gui/theme_manager.py
"""
ThemeManager — central colour palette, typography, spacing and theme switching.
All GUI files must import colours AND layout tokens from here.
No hardcoded hex values, font sizes, or spacing integers elsewhere.

Usage:
    from gui.theme_manager import theme_manager

    c   = theme_manager.palette     # colour tokens  → c.BLUE, c.BG_PANEL …
    ty  = theme_manager.typography  # font tokens     → ty.FONT_UI, ty.SIZE_BODY …
    sp  = theme_manager.spacing     # spacing tokens  → sp.GAP_SM, sp.RADIUS_MD …

    # React to theme changes
    theme_manager.theme_changed.connect(self.apply_theme)

    # Change density (compact / normal / relaxed)
    theme_manager.set_density("compact")   # for smaller screens / more data
"""

import logging
from typing import Dict, Callable, List, Optional
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox

logger = logging.getLogger(__name__)


# =============================================================================
# COLOUR PALETTES
# =============================================================================

class _Palette:
    """Immutable colour token bag for one theme variant."""

    def __init__(self, tokens: Dict[str, str]):
        self._tokens = tokens

    def __getattr__(self, name: str) -> str:
        try:
            return self._tokens[name]
        except KeyError:
            raise AttributeError(
                f"Colour token '{name}' not defined in palette. "
                f"Available: {', '.join(self._tokens)}"
            )

    def get(self, name: str, default: str = "#000000") -> str:
        return self._tokens.get(name, default)

    def as_dict(self) -> Dict[str, str]:
        return dict(self._tokens)


# ── Dark palette (GitHub Dark) ────────────────────────────────────────────────
DARK_TOKENS: Dict[str, str] = {
    # Backgrounds
    "BG_MAIN":       "#0d1117",
    "BG_PANEL":      "#161b22",
    "BG_ROW_A":      "#1c2128",
    "BG_ROW_B":      "#22272e",
    "BG_HOVER":      "#21262d",
    "BG_INPUT":      "#0d1117",
    "BG_SELECTED":   "#1f3147",   # selected row / item

    # Borders
    "BORDER":        "#30363d",
    "BORDER_DIM":   "#30363d",
    "BORDER_FOCUS":  "#58a6ff",
    "BORDER_STRONG": "#484f58",

    # Text
    "TEXT_MAIN":     "#e6edf3",
    "TEXT_DIM":      "#8b949e",
    "TEXT_DISABLED": "#484f58",
    "TEXT_INVERSE":  "#0d1117",
    "TEXT_LINK":     "#58a6ff",

    # Trading / semantic (adjusted for dark background)
    "GREEN":         "#2ea043",
    "GREEN_BRIGHT":  "#3fb950",
    "RED":           "#da3633",
    "RED_BRIGHT":    "#f85149",
    "YELLOW":        "#d29922",
    "YELLOW_BRIGHT": "#e3b341",
    "BLUE":          "#58a6ff",
    "BLUE_DARK":     "#1f6feb",
    "ORANGE":        "#ffa657",
    "PURPLE":        "#bc8cff",

    # Status bar / toolbar
    "BAR_BG":        "#161b22",
    "BAR_BORDER":    "#30363d",

    # Chart-specific
    "CHART_BG":      "#0d1117",
    "CHART_GRID":    "#21262d",
    "CHART_AXIS":    "#8b949e",
    "CHART_CANDLE_UP":   "#2ea043",
    "CHART_CANDLE_DOWN": "#f85149",
}

# ── Light palette (GitHub Light) ──────────────────────────────────────────────
LIGHT_TOKENS: Dict[str, str] = {
    # Backgrounds
    "BG_MAIN":       "#ffffff",
    "BG_PANEL":      "#f6f8fa",
    "BG_ROW_A":      "#ffffff",
    "BG_ROW_B":      "#f6f8fa",
    "BG_HOVER":      "#eaeef2",
    "BG_INPUT":      "#ffffff",
    "BG_SELECTED":   "#dbeafe",   # selected row / item

    # Borders
    "BORDER":        "#d0d7de",
    "BORDER_DIM":   "#d0d7de",
    "BORDER_FOCUS":  "#0969da",
    "BORDER_STRONG": "#8c959f",

    # Text
    "TEXT_MAIN":     "#1f2328",
    "TEXT_DIM":      "#636c76",
    "TEXT_DISABLED": "#afb8c1",
    "TEXT_INVERSE":  "#ffffff",
    "TEXT_LINK":     "#0969da",

    # Trading / semantic (darker shades for readability on white)
    "GREEN":         "#1a7f37",
    "GREEN_BRIGHT":  "#2da44e",
    "RED":           "#cf222e",
    "RED_BRIGHT":    "#a40e26",
    "YELLOW":        "#9a6700",
    "YELLOW_BRIGHT": "#bf8700",
    "BLUE":          "#0969da",
    "BLUE_DARK":     "#0550ae",
    "ORANGE":        "#bc4c00",
    "PURPLE":        "#8250df",

    # Status bar / toolbar
    "BAR_BG":        "#f6f8fa",
    "BAR_BORDER":    "#d0d7de",

    # Chart-specific
    "CHART_BG":      "#ffffff",
    "CHART_GRID":    "#eaeef2",
    "CHART_AXIS":    "#636c76",
    "CHART_CANDLE_UP":   "#1a7f37",
    "CHART_CANDLE_DOWN": "#cf222e",
}


# =============================================================================
# TYPOGRAPHY
# =============================================================================

class _Typography:
    """
    Font-family, size, weight and line-height tokens.

    All sizes are in points (pt) so they scale correctly on HiDPI displays.
    Use these in setStyleSheet via:  f"font-size: {ty.SIZE_BODY}pt;"
    Use in QFont via:                QFont(ty.FONT_UI, ty.SIZE_BODY)
    """

    def __init__(self, tokens: Dict[str, object]):
        self._tokens = tokens

    def __getattr__(self, name: str):
        try:
            return self._tokens[name]
        except KeyError:
            raise AttributeError(
                f"Typography token '{name}' not defined. "
                f"Available: {', '.join(str(k) for k in self._tokens)}"
            )

    def get(self, name: str, default=None):
        return self._tokens.get(name, default)

    def as_dict(self) -> Dict[str, object]:
        return dict(self._tokens)


# ── Typography token sets (density-independent) ───────────────────────────────
#
# One typography object is shared between dark and light — only colours change
# per theme, not type scales.  Density (compact / normal / relaxed) does change
# the scale and is handled separately below.

# Shared across ALL densities — only the SIZE_* values are overridden per density
_TYPOGRAPHY_BASE: Dict[str, object] = {
    # Families
    "FONT_UI":       "Segoe UI",            # All UI elements
    "FONT_MONO":     "Consolas, Monaco, 'Courier New', monospace",  # Logs / code
    "FONT_NUMERIC":  "Consolas, 'Courier New', monospace",  # P&L, prices (monospaced digits)

    # Weights (CSS keyword strings, usable in stylesheets)
    "WEIGHT_NORMAL":  "normal",   # 400
    "WEIGHT_MEDIUM":  "500",      # medium — not a CSS keyword, use numeric
    "WEIGHT_BOLD":    "bold",     # 700
    "WEIGHT_HEAVY":   "800",

    # Line heights (unitless multiplier — multiply by font size for px value)
    "LINE_HEIGHT_TIGHT":   1.2,   # Labels, table cells — pack data closely
    "LINE_HEIGHT_NORMAL":  1.4,   # General UI text
    "LINE_HEIGHT_RELAXED": 1.6,   # Onboarding text, descriptions
    "LINE_HEIGHT_LOG":     1.3,   # Log widget — readable but dense

    # Letter spacing (pt, for use in stylesheet: letter-spacing: Xpt)
    "LETTER_TIGHT":  "-0.3px",
    "LETTER_NORMAL": "0px",
    "LETTER_WIDE":   "0.5px",     # All-caps labels, status badges
}

# ── Normal density type scale (default) ───────────────────────────────────────
TYPOGRAPHY_NORMAL: Dict[str, object] = {
    **_TYPOGRAPHY_BASE,

    # Size scale (points)
    "SIZE_XS":      8,    # Copyright, footnotes, badges
    "SIZE_SM":      9,    # Table cells, status bar labels, dim metadata
    "SIZE_BODY":    10,   # Default body text, button labels
    "SIZE_MD":      11,   # Status messages, log text
    "SIZE_LG":      12,   # Section headers, card titles
    "SIZE_XL":      14,   # Panel headings
    "SIZE_2XL":     16,   # Section titles, P&L totals
    "SIZE_3XL":     20,   # Splash app name
    "SIZE_DISPLAY": 24,   # Large metric display (e.g. index price)
    "SIZE_MONO":    10,   # Log / code monospace body
    "SIZE_NUMERIC": 11,   # Price / P&L figures
}

# ── Compact density type scale (smaller screens / more data) ──────────────────
TYPOGRAPHY_COMPACT: Dict[str, object] = {
    **_TYPOGRAPHY_BASE,

    "SIZE_XS":      7,
    "SIZE_SM":      8,
    "SIZE_BODY":    9,
    "SIZE_MD":      9,
    "SIZE_LG":      10,
    "SIZE_XL":      11,
    "SIZE_2XL":     13,
    "SIZE_3XL":     17,
    "SIZE_DISPLAY": 20,
    "SIZE_MONO":    8,
    "SIZE_NUMERIC": 9,
}

# ── Relaxed density type scale (large monitors / accessibility) ───────────────
TYPOGRAPHY_RELAXED: Dict[str, object] = {
    **_TYPOGRAPHY_BASE,

    "SIZE_XS":      9,
    "SIZE_SM":      10,
    "SIZE_BODY":    11,
    "SIZE_MD":      12,
    "SIZE_LG":      13,
    "SIZE_XL":      15,
    "SIZE_2XL":     18,
    "SIZE_3XL":     22,
    "SIZE_DISPLAY": 28,
    "SIZE_MONO":    11,
    "SIZE_NUMERIC": 12,
}

_TYPOGRAPHY_MAP = {
    "normal":  TYPOGRAPHY_NORMAL,
    "compact": TYPOGRAPHY_COMPACT,
    "relaxed": TYPOGRAPHY_RELAXED,
}


# =============================================================================
# SPACING
# =============================================================================

class _Spacing:
    """
    Padding, margin, gap, border-radius and icon-size tokens.

    All values are integers (pixels).  Use them in:
      - setStyleSheet:      f"padding: {sp.PAD_SM}px {sp.PAD_MD}px;"
      - setContentsMargins: layout.setContentsMargins(sp.PAD_MD, sp.PAD_SM, sp.PAD_MD, sp.PAD_SM)
      - setSpacing:         layout.setSpacing(sp.GAP_SM)
      - setFixedHeight:     widget.setMinimumHeight(sp.ROW_HEIGHT)
    """

    def __init__(self, tokens: Dict[str, int]):
        self._tokens = tokens

    def __getattr__(self, name: str) -> int:
        try:
            return self._tokens[name]
        except KeyError:
            raise AttributeError(
                f"Spacing token '{name}' not defined. "
                f"Available: {', '.join(self._tokens)}"
            )

    def get(self, name: str, default: int = 0) -> int:
        return self._tokens.get(name, default)

    def as_dict(self) -> Dict[str, int]:
        return dict(self._tokens)


# ── Normal spacing scale ──────────────────────────────────────────────────────
SPACING_NORMAL: Dict[str, int] = {
    # Padding (inner whitespace)
    "PAD_XS":    2,    # Tight badges, tiny chips
    "PAD_SM":    4,    # Table cells, status bar items
    "PAD_MD":    8,    # Buttons, cards, inputs
    "PAD_LG":   12,    # Panel content areas
    "PAD_XL":   16,    # Dialog content, section padding
    "PAD_2XL":  24,    # Splash screen, onboarding

    # Gaps (space between siblings in layouts)
    "GAP_XS":    2,
    "GAP_SM":    4,
    "GAP_MD":    8,
    "GAP_LG":   12,
    "GAP_XL":   16,

    # Border radii
    "RADIUS_SM":   3,   # Tags, small badges
    "RADIUS_MD":   5,   # Buttons, inputs, cards
    "RADIUS_LG":   8,   # Panels, dialogs
    "RADIUS_XL":  12,   # Splash screen, large cards
    "RADIUS_PILL": 999, # Pill badges (mode label)

    # Component heights (min-height for consistent rows/buttons)
    "ROW_HEIGHT":      24,   # Table row height
    "BTN_HEIGHT_SM":   28,   # Small button
    "BTN_HEIGHT_MD":   36,   # Standard button
    "BTN_HEIGHT_LG":   44,   # Large / primary button
    "INPUT_HEIGHT":    32,   # Text inputs, combo boxes
    "STATUS_BAR_H":    44,   # App status bar
    "BUTTON_PANEL_H":  68,   # Button panel below chart
    "HEADER_H":        40,   # Panel / section headers
    "TAB_H":           36,   # Tab bar height

    # Icon sizes
    "ICON_SM":   12,
    "ICON_MD":   16,
    "ICON_LG":   20,
    "ICON_XL":   24,

    # Separator thickness
    "SEPARATOR":  1,

    # Splitter handle width
    "SPLITTER":   2,

    # Progress bar heights
    "PROGRESS_SM":  4,
    "PROGRESS_MD":  8,
    "PROGRESS_LG": 12,
}

# ── Compact spacing scale ─────────────────────────────────────────────────────
SPACING_COMPACT: Dict[str, int] = {
    "PAD_XS":    1,
    "PAD_SM":    3,
    "PAD_MD":    6,
    "PAD_LG":    8,
    "PAD_XL":   12,
    "PAD_2XL":  16,

    "GAP_XS":    1,
    "GAP_SM":    3,
    "GAP_MD":    5,
    "GAP_LG":    8,
    "GAP_XL":   10,

    "RADIUS_SM":   2,
    "RADIUS_MD":   4,
    "RADIUS_LG":   6,
    "RADIUS_XL":   8,
    "RADIUS_PILL": 999,

    "ROW_HEIGHT":      20,
    "BTN_HEIGHT_SM":   24,
    "BTN_HEIGHT_MD":   30,
    "BTN_HEIGHT_LG":   36,
    "INPUT_HEIGHT":    26,
    "STATUS_BAR_H":    36,
    "BUTTON_PANEL_H":  56,
    "HEADER_H":        32,
    "TAB_H":           28,

    "ICON_SM":   10,
    "ICON_MD":   14,
    "ICON_LG":   16,
    "ICON_XL":   20,

    "SEPARATOR":  1,
    "SPLITTER":   1,

    "PROGRESS_SM":  3,
    "PROGRESS_MD":  6,
    "PROGRESS_LG":  9,
}

# ── Relaxed spacing scale ─────────────────────────────────────────────────────
SPACING_RELAXED: Dict[str, int] = {
    "PAD_XS":    3,
    "PAD_SM":    6,
    "PAD_MD":   10,
    "PAD_LG":   16,
    "PAD_XL":   20,
    "PAD_2XL":  32,

    "GAP_XS":    3,
    "GAP_SM":    6,
    "GAP_MD":   10,
    "GAP_LG":   16,
    "GAP_XL":   20,

    "RADIUS_SM":   4,
    "RADIUS_MD":   6,
    "RADIUS_LG":  10,
    "RADIUS_XL":  16,
    "RADIUS_PILL": 999,

    "ROW_HEIGHT":      28,
    "BTN_HEIGHT_SM":   32,
    "BTN_HEIGHT_MD":   40,
    "BTN_HEIGHT_LG":   50,
    "INPUT_HEIGHT":    36,
    "STATUS_BAR_H":    52,
    "BUTTON_PANEL_H":  80,
    "HEADER_H":        48,
    "TAB_H":           42,

    "ICON_SM":   14,
    "ICON_MD":   18,
    "ICON_LG":   24,
    "ICON_XL":   28,

    "SEPARATOR":  1,
    "SPLITTER":   3,

    "PROGRESS_SM":  5,
    "PROGRESS_MD": 10,
    "PROGRESS_LG": 14,
}

_SPACING_MAP = {
    "normal":  SPACING_NORMAL,
    "compact": SPACING_COMPACT,
    "relaxed": SPACING_RELAXED,
}


# =============================================================================
# THEME MANAGER SINGLETON
# =============================================================================

class ThemeManager(QObject):
    """
    Singleton that manages the active colour theme, typography scale,
    and spacing density.  Emits signals when any of these change.

    Properties:
        palette     → _Palette   colour tokens
        typography  → _Typography  font/size/weight/line-height tokens
        spacing     → _Spacing   padding/gap/radius/height tokens

    Signals:
        theme_changed(str)    → "dark" | "light"
        density_changed(str)  → "compact" | "normal" | "relaxed"

    Quick access alias:
        c  = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing
    """

    theme_changed   = pyqtSignal(str)   # "dark" | "light"
    density_changed = pyqtSignal(str)   # "compact" | "normal" | "relaxed"

    _instance    = None
    _initialized = False

    # ── Singleton ──────────────────────────────────────────────────────────────

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ThemeManager._initialized:
            return
        super().__init__()
        ThemeManager._initialized = True

        self._current_theme   = "dark"
        self._current_density = "normal"

        self._palette    = _Palette(DARK_TOKENS)
        self._typography = _Typography(TYPOGRAPHY_NORMAL)
        self._spacing    = _Spacing(SPACING_NORMAL)

        logger.info("ThemeManager initialized (theme=dark, density=normal)")

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def palette(self) -> _Palette:
        """Active colour palette."""
        return self._palette

    @property
    def typography(self) -> _Typography:
        """Active typography scale."""
        return self._typography

    @property
    def spacing(self) -> _Spacing:
        """Active spacing scale."""
        return self._spacing

    # Convenience short aliases
    @property
    def c(self) -> _Palette:
        """Alias for palette — theme_manager.c.BLUE"""
        return self._palette

    @property
    def ty(self) -> _Typography:
        """Alias for typography — theme_manager.ty.SIZE_BODY"""
        return self._typography

    @property
    def sp(self) -> _Spacing:
        """Alias for spacing — theme_manager.sp.PAD_MD"""
        return self._spacing

    @property
    def current_theme(self) -> str:
        return self._current_theme

    @property
    def current_density(self) -> str:
        return self._current_density

    def is_dark(self) -> bool:
        return self._current_theme == "dark"

    def is_compact(self) -> bool:
        return self._current_density == "compact"

    # ── Theme control ──────────────────────────────────────────────────────────

    def set_theme(self, theme: str) -> None:
        """Switch to 'dark' or 'light'. Persists nothing — call save_preference() if needed."""
        try:
            theme = theme.lower().strip()
            if theme not in ("dark", "light"):
                logger.warning(f"[ThemeManager.set_theme] Unknown theme '{theme}', ignoring")
                return
            if theme == self._current_theme:
                return

            self._current_theme = theme
            self._palette = _Palette(DARK_TOKENS if theme == "dark" else LIGHT_TOKENS)

            app = QApplication.instance()
            if app:
                app.setStyleSheet(self._build_app_stylesheet())

            self.theme_changed.emit(theme)
            logger.info(f"[ThemeManager] Theme → '{theme}'")

        except Exception as e:
            logger.error(f"[ThemeManager.set_theme] Failed: {e}", exc_info=True)

    def toggle(self) -> None:
        """Toggle dark ↔ light."""
        self.set_theme("light" if self._current_theme == "dark" else "dark")

    # ── Density control ────────────────────────────────────────────────────────

    def set_density(self, density: str) -> None:
        """
        Switch the spacing and typography density.
        density: 'compact' | 'normal' | 'relaxed'

        Use 'compact' for small/dense screens or power users who want more data
        on screen at once.  Use 'relaxed' for accessibility / large monitors.
        """
        try:
            density = density.lower().strip()
            if density not in _SPACING_MAP:
                logger.warning(f"[ThemeManager.set_density] Unknown density '{density}', ignoring")
                return
            if density == self._current_density:
                return

            self._current_density = density
            self._typography = _Typography(_TYPOGRAPHY_MAP[density])
            self._spacing    = _Spacing(_SPACING_MAP[density])

            # Re-apply app stylesheet so global spacing tokens update
            app = QApplication.instance()
            if app:
                app.setStyleSheet(self._build_app_stylesheet())

            self.density_changed.emit(density)
            logger.info(f"[ThemeManager] Density → '{density}'")

        except Exception as e:
            logger.error(f"[ThemeManager.set_density] Failed: {e}", exc_info=True)

    # ── Persistence ────────────────────────────────────────────────────────────

    def save_preference(self) -> None:
        """Persist theme + density to QSettings."""
        try:
            from PyQt5.QtCore import QSettings
            s = QSettings("YourCompany", "AlgoTradingPro")
            s.setValue("theme",   self._current_theme)
            s.setValue("density", self._current_density)
            logger.debug(f"[ThemeManager] Preferences saved (theme={self._current_theme}, density={self._current_density})")
        except Exception as e:
            logger.warning(f"[ThemeManager.save_preference] Failed: {e}")

    def load_preference(self) -> None:
        """Load and apply persisted theme + density from QSettings."""
        try:
            from PyQt5.QtCore import QSettings
            s = QSettings("YourCompany", "AlgoTradingPro")
            theme   = s.value("theme",   "dark")
            density = s.value("density", "normal")
            self.set_density(density)
            self.set_theme(theme)
            logger.info(f"[ThemeManager] Preferences loaded (theme={theme}, density={density})")
        except Exception as e:
            logger.warning(f"[ThemeManager.load_preference] Failed: {e}")

    # ── Stylesheet builder ─────────────────────────────────────────────────────

    def _build_app_stylesheet(self) -> str:
        """
        Build the global QApplication stylesheet from the active palette,
        typography, and spacing tokens.

        This stylesheet covers all standard Qt widgets.  Individual widget
        classes should still call apply_theme() to handle custom styling
        that cannot be expressed in a global stylesheet.
        """
        c  = self._palette
        ty = self._typography
        sp = self._spacing

        return f"""
            /* ── Base ─────────────────────────────────────────────────────── */
            QMainWindow, QWidget, QDialog {{
                background:  {c.BG_MAIN};
                color:       {c.TEXT_MAIN};
                font-family: {ty.FONT_UI};
                font-size:   {ty.SIZE_BODY}pt;
            }}

            /* ── Menu bar ──────────────────────────────────────────────────── */
            QMenuBar {{
                background:    {c.BAR_BG};
                color:         {c.TEXT_MAIN};
                border-bottom: {sp.SEPARATOR}px solid {c.BAR_BORDER};
                font-size:     {ty.SIZE_BODY}pt;
                padding:       {sp.PAD_XS}px 0;
            }}
            QMenuBar::item {{
                padding:    {sp.PAD_SM}px {sp.PAD_MD}px;
                background: transparent;
            }}
            QMenuBar::item:selected {{ background: {c.BG_HOVER}; border-radius: {sp.RADIUS_SM}px; }}

            QMenu {{
                background:  {c.BG_PANEL};
                color:       {c.TEXT_MAIN};
                border:      {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                font-size:   {ty.SIZE_BODY}pt;
                padding:     {sp.PAD_SM}px 0;
            }}
            QMenu::item {{
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
            }}
            QMenu::item:selected {{ background: {c.BG_HOVER}; }}
            QMenu::separator {{
                height:     {sp.SEPARATOR}px;
                background: {c.BORDER};
                margin:     {sp.PAD_SM}px 0;
            }}

            /* ── Status bar ─────────────────────────────────────────────────── */
            QStatusBar {{
                background:  {c.BAR_BG};
                color:       {c.TEXT_DIM};
                border-top:  {sp.SEPARATOR}px solid {c.BAR_BORDER};
                font-size:   {ty.SIZE_SM}pt;
                min-height:  {sp.STATUS_BAR_H}px;
            }}

            /* ── Tooltips ────────────────────────────────────────────────────── */
            QToolTip {{
                background:    {c.BG_PANEL};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                border-radius: {sp.RADIUS_MD}px;
                font-size:     {ty.SIZE_SM}pt;
                font-family:   {ty.FONT_UI};
            }}

            /* ── Scroll bars ─────────────────────────────────────────────────── */
            QScrollBar:vertical {{
                background:    {c.BG_PANEL};
                width:         {sp.ICON_MD}px;
                border-radius: {sp.RADIUS_MD}px;
                border:        none;
            }}
            QScrollBar::handle:vertical {{
                background:    {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                min-height:    {sp.BTN_HEIGHT_SM}px;
            }}
            QScrollBar::handle:vertical:hover  {{ background: {c.BORDER_STRONG}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical      {{ height: 0; }}

            QScrollBar:horizontal {{
                background:    {c.BG_PANEL};
                height:        {sp.ICON_MD}px;
                border-radius: {sp.RADIUS_MD}px;
                border:        none;
            }}
            QScrollBar::handle:horizontal {{
                background:    {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                min-width:     {sp.BTN_HEIGHT_SM}px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {c.BORDER_STRONG}; }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal     {{ width: 0; }}

            /* ── Tabs ────────────────────────────────────────────────────────── */
            QTabWidget::pane {{
                border:     {sp.SEPARATOR}px solid {c.BORDER};
                background: {c.BG_MAIN};
            }}
            QTabBar::tab {{
                background:    {c.BG_PANEL};
                color:         {c.TEXT_DIM};
                padding:       {sp.PAD_SM}px {sp.PAD_LG}px;
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                min-width:     90px;
                max-width:     160px;
                font-size:     {ty.SIZE_SM}pt;
                font-weight:   {ty.WEIGHT_BOLD};
                min-height:    {sp.TAB_H}px;
            }}
            QTabBar::tab:selected {{
                background:    {c.BG_HOVER};
                color:         {c.TEXT_MAIN};
                border-bottom: 2px solid {c.BLUE};
            }}
            QTabBar::tab:hover:!selected {{ background: {c.BG_HOVER}; }}

            /* ── Tables ──────────────────────────────────────────────────────── */
            QTableWidget {{
                background:     {c.BG_PANEL};
                gridline-color: {c.BORDER};
                color:          {c.TEXT_MAIN};
                border:         {sp.SEPARATOR}px solid {c.BORDER};
                font-size:      {ty.SIZE_SM}pt;
            }}
            QTableWidget::item {{
                padding:     {sp.PAD_SM}px {sp.PAD_MD}px;
                min-height:  {sp.ROW_HEIGHT}px;
            }}
            QTableWidget::item:selected {{
                background: {c.BG_SELECTED};
                color:      {c.TEXT_MAIN};
            }}
            QHeaderView::section {{
                background:  {c.BG_HOVER};
                color:       {c.TEXT_DIM};
                border:      none;
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                padding:     {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:   {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
                letter-spacing: {ty.LETTER_WIDE};
                min-height:  {sp.HEADER_H}px;
            }}

            /* ── Inputs ──────────────────────────────────────────────────────── */
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
                background:    {c.BG_INPUT};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:     {ty.SIZE_BODY}pt;
                min-height:    {sp.INPUT_HEIGHT}px;
                selection-background-color: {c.BG_SELECTED};
            }}
            QLineEdit:focus, QComboBox:focus,
            QSpinBox:focus,  QDoubleSpinBox:focus {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
            }}
            QLineEdit:disabled, QComboBox:disabled,
            QSpinBox:disabled, QDoubleSpinBox:disabled {{
                color:      {c.TEXT_DISABLED};
                background: {c.BG_PANEL};
            }}
            QComboBox::drop-down {{
                border: none;
                width:  {sp.ICON_LG}px;
            }}

            /* ── Group boxes ─────────────────────────────────────────────────── */
            QGroupBox {{
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                margin-top:    {sp.PAD_MD}px;
                padding-top:   {sp.PAD_SM}px;
                font-weight:   {ty.WEIGHT_BOLD};
                font-size:     {ty.SIZE_SM}pt;
                color:         {c.TEXT_MAIN};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left:    {sp.PAD_MD}px;
                padding: 0 {sp.PAD_SM}px;
                color:   {c.BLUE};
                font-size: {ty.SIZE_SM}pt;
            }}

            /* ── Buttons ─────────────────────────────────────────────────────── */
            QPushButton {{
                background:    {c.BG_HOVER};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_LG}px;
                font-weight:   {ty.WEIGHT_BOLD};
                font-size:     {ty.SIZE_BODY}pt;
                min-height:    {sp.BTN_HEIGHT_MD}px;
            }}
            QPushButton:hover   {{ background: {c.BORDER}; }}
            QPushButton:pressed {{ background: {c.BG_ROW_B}; border-color: {c.BORDER_STRONG}; }}
            QPushButton:disabled {{
                background: {c.BG_PANEL};
                color:      {c.TEXT_DISABLED};
                border-color: {c.BORDER};
            }}

            /* ── Progress bars ───────────────────────────────────────────────── */
            QProgressBar {{
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                background:    {c.BG_PANEL};
                text-align:    center;
                color:         {c.TEXT_MAIN};
                font-size:     {ty.SIZE_XS}pt;
                min-height:    {sp.PROGRESS_MD}px;
                max-height:    {sp.PROGRESS_LG}px;
            }}
            QProgressBar::chunk {{
                background:    {c.BLUE};
                border-radius: {sp.RADIUS_SM}px;
            }}

            /* ── Labels ──────────────────────────────────────────────────────── */
            QLabel {{
                color:     {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
            }}

            /* ── Splitter ────────────────────────────────────────────────────── */
            QSplitter::handle {{
                background: {c.BORDER};
            }}
            QSplitter::handle:horizontal {{ width:  {sp.SPLITTER}px; }}
            QSplitter::handle:vertical   {{ height: {sp.SPLITTER}px; }}

            /* ── Checkboxes & Radio buttons ──────────────────────────────────── */
            QCheckBox, QRadioButton {{
                color:     {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                spacing:   {sp.GAP_SM}px;
            }}
            QCheckBox:disabled, QRadioButton:disabled {{
                color: {c.TEXT_DISABLED};
            }}

            /* ── Frames ──────────────────────────────────────────────────────── */
            QFrame[frameShape="4"],
            QFrame[frameShape="5"] {{
                color: {c.BORDER};
            }}
        """

    # ── Convenience stylesheet snippets for widget apply_theme() ──────────────

    def card_stylesheet(self,
                        radius_token: str = "RADIUS_MD",
                        bg_token: str = "BG_PANEL") -> str:
        """
        Return a QFrame card stylesheet using current tokens.
        Widgets can call this from apply_theme() instead of repeating the template.

        Example:
            self.setStyleSheet(theme_manager.card_stylesheet())
        """
        c  = self._palette
        sp = self._spacing
        return f"""
            QFrame {{
                background:    {c.get(bg_token, c.BG_PANEL)};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.get(radius_token, sp.RADIUS_MD)}px;
                padding:       {sp.PAD_SM}px;
            }}
        """

    def label_stylesheet(self,
                         color_token: str = "TEXT_MAIN",
                         size_token:  str = "SIZE_BODY",
                         bold: bool = False) -> str:
        """
        Return a QLabel stylesheet using current tokens.

        Example:
            self.value_label.setStyleSheet(
                theme_manager.label_stylesheet("BLUE", "SIZE_LG", bold=True)
            )
        """
        c  = self._palette
        ty = self._typography
        weight = ty.WEIGHT_BOLD if bold else ty.WEIGHT_NORMAL
        return (
            f"color: {c.get(color_token, c.TEXT_MAIN)}; "
            f"font-size: {ty.get(size_token, ty.SIZE_BODY)}pt; "
            f"font-weight: {weight}; "
            f"background: transparent; "
            f"border: none;"
        )

    def button_stylesheet(self,
                          bg_token:    str = "GREEN",
                          hover_token: str = "GREEN_BRIGHT",
                          min_width:   int = 100) -> str:
        """
        Return a semantic-coloured QPushButton stylesheet.

        Example:
            self.btn_start.setStyleSheet(
                theme_manager.button_stylesheet("GREEN", "GREEN_BRIGHT")
            )
            self.btn_stop.setStyleSheet(
                theme_manager.button_stylesheet("RED", "RED_BRIGHT")
            )
        """
        c  = self._palette
        ty = self._typography
        sp = self._spacing
        bg    = c.get(bg_token,    c.GREEN)
        hover = c.get(hover_token, c.GREEN_BRIGHT)
        return f"""
            QPushButton {{
                background:    {bg};
                color:         {c.TEXT_INVERSE};
                border:        none;
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_LG}px;
                font-weight:   {ty.WEIGHT_BOLD};
                font-size:     {ty.SIZE_BODY}pt;
                min-width:     {min_width}px;
                min-height:    {sp.BTN_HEIGHT_MD}px;
            }}
            QPushButton:hover   {{ background: {hover}; }}
            QPushButton:pressed {{ background: {bg}; border: 1px solid {c.BORDER_STRONG}; }}
            QPushButton:disabled {{
                background: {c.BG_HOVER};
                color:      {c.TEXT_DISABLED};
                border:     1px solid {c.BORDER};
            }}
        """

    def badge_stylesheet(self, color_token: str = "BLUE") -> str:
        """
        Return a pill-badge stylesheet (e.g., for mode label, status chips).

        Example:
            self.mode_label.setStyleSheet(theme_manager.badge_stylesheet("GREEN"))
        """
        c  = self._palette
        ty = self._typography
        sp = self._spacing
        bg = c.get(color_token, c.BLUE)
        return (
            f"color: {c.TEXT_INVERSE}; "
            f"background: {bg}; "
            f"border-radius: {sp.RADIUS_PILL}px; "
            f"padding: {sp.PAD_XS}px {sp.PAD_MD}px; "
            f"font-weight: {ty.WEIGHT_BOLD}; "
            f"font-size: {ty.SIZE_XS}pt; "
            f"letter-spacing: {ty.LETTER_WIDE};"
        )

    def log_stylesheet(self) -> str:
        """
        Return a stylesheet for log text widgets (QTextEdit / QPlainTextEdit).

        Example:
            self.log_widget.setStyleSheet(theme_manager.log_stylesheet())
        """
        c  = self._palette
        ty = self._typography
        sp = self._spacing
        return f"""
            QTextEdit, QPlainTextEdit {{
                background:  {c.BG_MAIN};
                color:       {c.TEXT_MAIN};
                border:      {sp.SEPARATOR}px solid {c.BORDER};
                font-family: {ty.FONT_MONO};
                font-size:   {ty.SIZE_MONO}pt;
                line-height: {ty.LINE_HEIGHT_LOG};
                padding:     {sp.PAD_SM}px;
                selection-background-color: {c.BG_SELECTED};
            }}
        """


# Module-level singleton — import this everywhere
theme_manager = ThemeManager()


# Add this helper function near the top of main.py after the imports:

def show_themed_message_box(parent, title, text, buttons=QMessageBox.Ok, icon=QMessageBox.NoIcon):
    """
    Show a message box with proper theme styling.

    Args:
        parent: Parent widget (can be None)
        title: Window title
        text: Message text
        buttons: QMessageBox button flags
        icon: QMessageBox icon

    Returns:
        QMessageBox.StandardButton: The button that was clicked
    """
    try:
        from gui.theme_manager import theme_manager

        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(buttons)
        msg_box.setIcon(icon)

        # Apply theme
        c = theme_manager.palette
        ty = theme_manager.typography
        sp = theme_manager.spacing

        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {c.BG_MAIN};
                color: {c.TEXT_MAIN};
            }}
            QMessageBox QLabel {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                min-width: 300px;
            }}
            QPushButton {{
                background-color: {c.BG_PANEL};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                min-width: 80px;
                font-size: {ty.SIZE_BODY}pt;
            }}
            QPushButton:hover {{
                background-color: {c.BG_HOVER};
                border-color: {c.BORDER_FOCUS};
            }}
            QPushButton:pressed {{
                background-color: {c.BORDER};
            }}
            QMessageBox QPushButton[text="Yes"], 
            QMessageBox QPushButton[text="OK"] {{
                background-color: {c.GREEN};
                color: white;
            }}
            QMessageBox QPushButton[text="Yes"]:hover,
            QMessageBox QPushButton[text="OK"]:hover {{
                background-color: {c.GREEN_BRIGHT};
            }}
            QMessageBox QPushButton[text="No"],
            QMessageBox QPushButton[text="Cancel"] {{
                background-color: {c.RED};
                color: white;
            }}
            QMessageBox QPushButton[text="No"]:hover,
            QMessageBox QPushButton[text="Cancel"]:hover {{
                background-color: {c.RED_BRIGHT};
            }}
        """)

        return msg_box.exec_()

    except Exception as e:
        logger.error(f"[show_themed_message_box] Failed: {e}", exc_info=True)
        # Fallback to regular QMessageBox
        return QMessageBox.question(parent, title, text, buttons)