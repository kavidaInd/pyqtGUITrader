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


# ── Dark palette (deep professional trading terminal aesthetic) ───────────────
DARK_TOKENS: Dict[str, str] = {
    # Backgrounds — rich layered depth
    "BG_MAIN":       "#0a0e1a",   # Deepest navy — main canvas
    "BG_PANEL":      "#111827",   # Panel background
    "BG_CARD":       "#161d2e",   # Card / elevated surface
    "BG_ROW_A":      "#111827",
    "BG_ROW_B":      "#151c2e",
    "BG_HOVER":      "#1c2742",   # Richer hover
    "BG_INPUT":      "#0d1220",   # Input fields
    "BG_SELECTED":   "#1a3a5c",   # Selected rows / items
    "BG_ELEVATED":   "#1e2840",   # Floating elements

    # Borders — subtle, layered
    "BORDER":        "#2a3550",
    "BORDER_DIM":    "#1f2d45",
    "BORDER_FOCUS":  "#4f8ef7",
    "BORDER_STRONG": "#3d5080",
    "BORDER_ACCENT": "#2563eb33",  # Semi-transparent blue glow

    # Text — crisp hierarchy
    "TEXT_MAIN":     "#e8edf5",
    "TEXT_DIM":      "#7b8db0",
    "TEXT_MUTED":    "#4a5878",
    "TEXT_DISABLED": "#374260",
    "TEXT_INVERSE":  "#0a0e1a",
    "TEXT_LINK":     "#4f8ef7",
    "TEXT_BRIGHT":   "#f0f4ff",

    # Trading / semantic — vivid, professional
    "GREEN":         "#10b981",
    "GREEN_BRIGHT":  "#34d399",
    "GREEN_GLOW":    "#10b98122",
    "RED":           "#ef4444",
    "RED_BRIGHT":    "#f87171",
    "RED_GLOW":      "#ef444422",
    "YELLOW":        "#f59e0b",
    "YELLOW_BRIGHT": "#fbbf24",
    "YELLOW_GLOW":   "#f59e0b22",
    "BLUE":          "#4f8ef7",
    "BLUE_BRIGHT":   "#6ba3ff",
    "BLUE_DARK":     "#2563eb",
    "BLUE_GLOW":     "#4f8ef722",
    "ORANGE":        "#f97316",
    "ORANGE_GLOW":   "#f9731622",
    "PURPLE":        "#a78bfa",
    "PURPLE_DARK":   "#7c3aed",
    "CYAN":          "#22d3ee",
    "TEAL":          "#14b8a6",

    # Status bar / toolbar
    "BAR_BG":        "#0d1220",
    "BAR_BORDER":    "#1f2d45",

    # Chart-specific
    "CHART_BG":          "#0a0e1a",
    "CHART_GRID":        "#141e35",
    "CHART_AXIS":        "#4a5878",
    "CHART_CANDLE_UP":   "#10b981",
    "CHART_CANDLE_DOWN": "#ef4444",

    # PnL widget specific
    "PNL_CARD_BG":  "#111827",
    "PNL_ACCENT":   "#2563eb",
    "PNL_DIVIDER":  "#2a3550",

    # Gradient stops (for use in qlineargradient)
    "GRAD_START":   "#0a0e1a",
    "GRAD_MID":     "#111827",
    "GRAD_END":     "#161d2e",

    # Shadow / glow approximation via bg colors
    "SHADOW":       "#00000055",
    "GLOW_BLUE":    "#4f8ef715",
    "GLOW_GREEN":   "#10b98115",
}

# ── Light palette (clean, high-contrast professional) ─────────────────────────
LIGHT_TOKENS: Dict[str, str] = {
    # Backgrounds
    "BG_MAIN":       "#f8fafc",
    "BG_PANEL":      "#ffffff",
    "BG_CARD":       "#f1f5f9",
    "BG_ROW_A":      "#ffffff",
    "BG_ROW_B":      "#f8fafc",
    "BG_HOVER":      "#e2e8f4",
    "BG_INPUT":      "#ffffff",
    "BG_SELECTED":   "#dbeafe",
    "BG_ELEVATED":   "#ffffff",

    # Borders
    "BORDER":        "#cbd5e1",
    "BORDER_DIM":    "#e2e8f0",
    "BORDER_FOCUS":  "#2563eb",
    "BORDER_STRONG": "#94a3b8",
    "BORDER_ACCENT": "#2563eb33",

    # Text
    "TEXT_MAIN":     "#0f172a",
    "TEXT_DIM":      "#475569",
    "TEXT_MUTED":    "#94a3b8",
    "TEXT_DISABLED": "#cbd5e1",
    "TEXT_INVERSE":  "#ffffff",
    "TEXT_LINK":     "#2563eb",
    "TEXT_BRIGHT":   "#020617",

    # Trading / semantic
    "GREEN":         "#059669",
    "GREEN_BRIGHT":  "#10b981",
    "GREEN_GLOW":    "#05966922",
    "RED":           "#dc2626",
    "RED_BRIGHT":    "#ef4444",
    "RED_GLOW":      "#dc262622",
    "YELLOW":        "#d97706",
    "YELLOW_BRIGHT": "#f59e0b",
    "YELLOW_GLOW":   "#d9770622",
    "BLUE":          "#2563eb",
    "BLUE_BRIGHT":   "#3b82f6",
    "BLUE_DARK":     "#1d4ed8",
    "BLUE_GLOW":     "#2563eb22",
    "ORANGE":        "#ea580c",
    "ORANGE_GLOW":   "#ea580c22",
    "PURPLE":        "#7c3aed",
    "PURPLE_DARK":   "#6d28d9",
    "CYAN":          "#0891b2",
    "TEAL":          "#0d9488",

    # Status bar / toolbar
    "BAR_BG":        "#f1f5f9",
    "BAR_BORDER":    "#e2e8f0",

    # Chart-specific
    "CHART_BG":          "#ffffff",
    "CHART_GRID":        "#f1f5f9",
    "CHART_AXIS":        "#94a3b8",
    "CHART_CANDLE_UP":   "#059669",
    "CHART_CANDLE_DOWN": "#dc2626",

    # PnL widget specific
    "PNL_CARD_BG":  "#f8fafc",
    "PNL_ACCENT":   "#2563eb",
    "PNL_DIVIDER":  "#e2e8f0",

    # Gradient stops
    "GRAD_START":   "#f8fafc",
    "GRAD_MID":     "#ffffff",
    "GRAD_END":     "#f1f5f9",

    "SHADOW":       "#00000015",
    "GLOW_BLUE":    "#2563eb10",
    "GLOW_GREEN":   "#05966910",
}


# =============================================================================
# TYPOGRAPHY
# =============================================================================

class _Typography:
    """Font-family, size, weight and line-height tokens."""

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


_TYPOGRAPHY_BASE: Dict[str, object] = {
    # Families — refined trading terminal feel
    "FONT_UI":       "Segoe UI",
    "FONT_DISPLAY":  "Segoe UI Semibold, Segoe UI, sans-serif",
    "FONT_MONO":     "Consolas, 'Cascadia Code', Monaco, 'Courier New', monospace",
    "FONT_NUMERIC":  "Consolas, 'Cascadia Code', 'Courier New', monospace",

    # Weights
    "WEIGHT_NORMAL":  "normal",
    "WEIGHT_MEDIUM":  "500",
    "WEIGHT_SEMIBOLD": "600",
    "WEIGHT_BOLD":    "bold",
    "WEIGHT_HEAVY":   "800",

    # Line heights
    "LINE_HEIGHT_TIGHT":   1.2,
    "LINE_HEIGHT_NORMAL":  1.4,
    "LINE_HEIGHT_RELAXED": 1.6,
    "LINE_HEIGHT_LOG":     1.3,

    # Letter spacing
    "LETTER_TIGHT":  "-0.3px",
    "LETTER_NORMAL": "0px",
    "LETTER_WIDE":   "0.5px",
    "LETTER_CAPS":   "0.8px",  # ALL-CAPS labels
}

TYPOGRAPHY_NORMAL: Dict[str, object] = {
    **_TYPOGRAPHY_BASE,
    "SIZE_XS":      8,
    "SIZE_SM":      9,
    "SIZE_BODY":    10,
    "SIZE_MD":      11,
    "SIZE_LG":      12,
    "SIZE_XL":      14,
    "SIZE_2XL":     16,
    "SIZE_3XL":     20,
    "SIZE_DISPLAY": 24,
    "SIZE_MONO":    10,
    "SIZE_NUMERIC": 11,
}

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
    """Padding, margin, gap, border-radius and icon-size tokens."""

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


SPACING_NORMAL: Dict[str, int] = {
    # Padding
    "PAD_XS":    2,
    "PAD_SM":    4,
    "PAD_MD":    8,
    "PAD_LG":   12,
    "PAD_XL":   16,
    "PAD_2XL":  24,

    # Gaps
    "GAP_XS":    2,
    "GAP_SM":    4,
    "GAP_MD":    8,
    "GAP_LG":   12,
    "GAP_XL":   16,

    # Border radii — refined, modern
    "RADIUS_SM":   4,
    "RADIUS_MD":   6,
    "RADIUS_LG":   10,
    "RADIUS_XL":   14,
    "RADIUS_PILL": 999,

    # Component heights
    "ROW_HEIGHT":      26,
    "BTN_HEIGHT_SM":   28,
    "BTN_HEIGHT_MD":   36,
    "BTN_HEIGHT_LG":   44,
    "INPUT_HEIGHT":    34,
    "STATUS_BAR_H":    44,
    "BUTTON_PANEL_H":  68,
    "HEADER_H":        40,
    "TAB_H":           36,
    "PNL_WIDGET_H":    100,

    # Icon sizes
    "ICON_SM":   12,
    "ICON_MD":   16,
    "ICON_LG":   20,
    "ICON_XL":   24,

    # Separator
    "SEPARATOR":  1,
    "SPLITTER":   2,

    # Progress bars
    "PROGRESS_SM":  4,
    "PROGRESS_MD":  8,
    "PROGRESS_LG": 12,
}

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
    "RADIUS_SM":   3,
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
    "PNL_WIDGET_H":    82,
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
    "RADIUS_SM":   5,
    "RADIUS_MD":   8,
    "RADIUS_LG":  12,
    "RADIUS_XL":  18,
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
    "PNL_WIDGET_H":    120,
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
    and spacing density.
    """

    theme_changed   = pyqtSignal(str)
    density_changed = pyqtSignal(str)

    _instance    = None
    _initialized = False

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
        return self._palette

    @property
    def typography(self) -> _Typography:
        return self._typography

    @property
    def spacing(self) -> _Spacing:
        return self._spacing

    @property
    def c(self) -> _Palette:
        return self._palette

    @property
    def ty(self) -> _Typography:
        return self._typography

    @property
    def sp(self) -> _Spacing:
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
        self.set_theme("light" if self._current_theme == "dark" else "dark")

    # ── Density control ────────────────────────────────────────────────────────

    def set_density(self, density: str) -> None:
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

            app = QApplication.instance()
            if app:
                app.setStyleSheet(self._build_app_stylesheet())

            self.density_changed.emit(density)
            logger.info(f"[ThemeManager] Density → '{density}'")

        except Exception as e:
            logger.error(f"[ThemeManager.set_density] Failed: {e}", exc_info=True)

    # ── Persistence ────────────────────────────────────────────────────────────

    def save_preference(self) -> None:
        try:
            from PyQt5.QtCore import QSettings
            s = QSettings("YourCompany", "AlgoTradingPro")
            s.setValue("theme",   self._current_theme)
            s.setValue("density", self._current_density)
            logger.debug(f"[ThemeManager] Preferences saved")
        except Exception as e:
            logger.warning(f"[ThemeManager.save_preference] Failed: {e}")

    def load_preference(self) -> None:
        try:
            from PyQt5.QtCore import QSettings
            s = QSettings("YourCompany", "AlgoTradingPro")
            theme   = s.value("theme",   "dark")
            density = s.value("density", "normal")
            self.set_density(density)
            self.set_theme(theme)
            self.apply_startup_theme()
            logger.info(f"[ThemeManager] Preferences loaded (theme={theme}, density={density})")
        except Exception as e:
            logger.warning(f"[ThemeManager.load_preference] Failed: {e}")

    def apply_startup_theme(self) -> None:
        try:
            app = QApplication.instance()
            if app:
                app.setStyleSheet(self._build_app_stylesheet())
            self.theme_changed.emit(self._current_theme)
            self.density_changed.emit(self._current_density)
            logger.info(
                f"[ThemeManager] Startup theme applied "
                f"(theme={self._current_theme}, density={self._current_density})"
            )
        except Exception as e:
            logger.error(f"[ThemeManager.apply_startup_theme] Failed: {e}", exc_info=True)

    # ── Stylesheet builder ─────────────────────────────────────────────────────

    def _build_app_stylesheet(self) -> str:
        """
        Build the global QApplication stylesheet from the active palette,
        typography, and spacing tokens. Professional trading terminal aesthetic.
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
                font-weight:   {ty.WEIGHT_MEDIUM};
            }}
            QMenuBar::item {{
                padding:    {sp.PAD_SM}px {sp.PAD_MD}px;
                background: transparent;
                border-radius: {sp.RADIUS_SM}px;
                margin: 0 2px;
            }}
            QMenuBar::item:selected {{
                background: {c.BG_HOVER};
                color: {c.TEXT_BRIGHT};
            }}

            QMenu {{
                background:  {c.BG_CARD};
                color:       {c.TEXT_MAIN};
                border:      {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                font-size:   {ty.SIZE_BODY}pt;
                padding:     {sp.PAD_SM}px 0;
            }}
            QMenu::item {{
                padding: {sp.PAD_SM}px {sp.PAD_XL}px;
                border-radius: {sp.RADIUS_SM}px;
                margin: 1px {sp.PAD_XS}px;
            }}
            QMenu::item:selected {{
                background: {c.BG_HOVER};
                color: {c.TEXT_BRIGHT};
            }}
            QMenu::separator {{
                height:     {sp.SEPARATOR}px;
                background: {c.BORDER_DIM};
                margin:     {sp.PAD_SM}px {sp.PAD_MD}px;
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
                background:    {c.BG_ELEVATED};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                border-radius: {sp.RADIUS_MD}px;
                font-size:     {ty.SIZE_SM}pt;
                font-family:   {ty.FONT_UI};
            }}

            /* ── Scroll bars ─────────────────────────────────────────────────── */
            QScrollBar:vertical {{
                background:    {c.BG_MAIN};
                width:         8px;
                border-radius: 4px;
                border:        none;
                margin: 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background:    {c.BORDER};
                border-radius: 4px;
                min-height:    {sp.BTN_HEIGHT_SM}px;
            }}
            QScrollBar::handle:vertical:hover  {{ background: {c.BORDER_STRONG}; }}
            QScrollBar::handle:vertical:pressed {{ background: {c.BLUE}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical      {{ height: 0; border: none; }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical      {{ background: none; }}

            QScrollBar:horizontal {{
                background:    {c.BG_MAIN};
                height:        8px;
                border-radius: 4px;
                border:        none;
                margin: 0 2px;
            }}
            QScrollBar::handle:horizontal {{
                background:    {c.BORDER};
                border-radius: 4px;
                min-width:     {sp.BTN_HEIGHT_SM}px;
            }}
            QScrollBar::handle:horizontal:hover  {{ background: {c.BORDER_STRONG}; }}
            QScrollBar::handle:horizontal:pressed {{ background: {c.BLUE}; }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal     {{ width: 0; border: none; }}
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal     {{ background: none; }}

            /* ── Tabs ────────────────────────────────────────────────────────── */
            QTabWidget::pane {{
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: 0 0 {sp.RADIUS_MD}px {sp.RADIUS_MD}px;
                background:    {c.BG_MAIN};
                top: -1px;
            }}
            QTabBar {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                background:    {c.BG_PANEL};
                color:         {c.TEXT_DIM};
                padding:       {sp.PAD_SM}px {sp.PAD_LG}px;
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-bottom: none;
                border-radius: {sp.RADIUS_MD}px {sp.RADIUS_MD}px 0 0;
                min-width:     90px;
                max-width:     160px;
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
                color: {c.TEXT_MAIN};
            }}

            /* ── Tables ──────────────────────────────────────────────────────── */
            QTableWidget {{
                background:     {c.BG_PANEL};
                alternate-background-color: {c.BG_ROW_B};
                gridline-color: {c.BORDER_DIM};
                color:          {c.TEXT_MAIN};
                border:         {sp.SEPARATOR}px solid {c.BORDER};
                border-radius:  {sp.RADIUS_MD}px;
                font-size:      {ty.SIZE_SM}pt;
                selection-background-color: {c.BG_SELECTED};
                outline: none;
            }}
            QTableWidget::item {{
                padding:     {sp.PAD_SM}px {sp.PAD_MD}px;
                min-height:  {sp.ROW_HEIGHT}px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background: {c.BG_SELECTED};
                color:      {c.TEXT_BRIGHT};
            }}
            QTableWidget::item:hover {{
                background: {c.BG_HOVER};
            }}
            QHeaderView {{
                border: none;
                background: transparent;
            }}
            QHeaderView::section {{
                background:  {c.BG_CARD};
                color:       {c.TEXT_DIM};
                border:      none;
                border-right:  {sp.SEPARATOR}px solid {c.BORDER_DIM};
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                padding:     {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:   {ty.SIZE_XS}pt;
                font-weight: {ty.WEIGHT_BOLD};
                letter-spacing: {ty.LETTER_CAPS};
                text-transform: uppercase;
                min-height:  {sp.HEADER_H}px;
            }}
            QHeaderView::section:first {{
                border-radius: {sp.RADIUS_MD}px 0 0 0;
            }}
            QHeaderView::section:last {{
                border-right: none;
                border-radius: 0 {sp.RADIUS_MD}px 0 0;
            }}

            /* ── Inputs ──────────────────────────────────────────────────────── */
            QLineEdit, QSpinBox, QDoubleSpinBox {{
                background:    {c.BG_INPUT};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:     {ty.SIZE_BODY}pt;
                min-height:    {sp.INPUT_HEIGHT}px;
                selection-background-color: {c.BG_SELECTED};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: {sp.SEPARATOR}px solid {c.BORDER_FOCUS};
                background: {c.BG_INPUT};
            }}
            QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
                color:      {c.TEXT_DISABLED};
                background: {c.BG_PANEL};
                border-color: {c.BORDER_DIM};
            }}

            QComboBox {{
                background:    {c.BG_INPUT};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:     {ty.SIZE_BODY}pt;
                min-height:    {sp.INPUT_HEIGHT}px;
                selection-background-color: {c.BG_SELECTED};
            }}
            QComboBox:focus {{
                border-color: {c.BORDER_FOCUS};
            }}
            QComboBox:disabled {{
                color: {c.TEXT_DISABLED};
                background: {c.BG_PANEL};
            }}
            QComboBox::drop-down {{
                border: none;
                width:  {sp.ICON_LG}px;
                subcontrol-origin: padding;
                subcontrol-position: right center;
            }}
            QComboBox QAbstractItemView {{
                background:   {c.BG_CARD};
                color:        {c.TEXT_MAIN};
                border:       {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                selection-background-color: {c.BG_HOVER};
                padding: {sp.PAD_XS}px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                border-radius: {sp.RADIUS_SM}px;
                margin: 1px 2px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {c.BG_HOVER};
            }}

            QTextEdit, QPlainTextEdit {{
                background:    {c.BG_INPUT};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:     {ty.SIZE_BODY}pt;
                selection-background-color: {c.BG_SELECTED};
            }}
            QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {c.BORDER_FOCUS};
            }}

            /* ── SpinBox buttons ─────────────────────────────────────────────── */
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                border: none;
                width: {sp.ICON_LG}px;
                background: {c.BG_HOVER};
                border-radius: {sp.RADIUS_SM}px;
            }}
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background: {c.BORDER};
            }}

            /* ── Group boxes ─────────────────────────────────────────────────── */
            QGroupBox {{
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                margin-top:    {sp.PAD_LG}px;
                padding-top:   {sp.PAD_MD}px;
                font-weight:   {ty.WEIGHT_BOLD};
                font-size:     {ty.SIZE_SM}pt;
                color:         {c.TEXT_MAIN};
                background:    {c.BG_PANEL};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left:    {sp.PAD_MD}px;
                padding: 0 {sp.PAD_SM}px;
                color:   {c.BLUE};
                font-size: {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_SEMIBOLD};
                background: {c.BG_MAIN};
            }}

            /* ── Buttons ─────────────────────────────────────────────────────── */
            QPushButton {{
                background:    {c.BG_CARD};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_LG}px;
                font-weight:   {ty.WEIGHT_SEMIBOLD};
                font-size:     {ty.SIZE_BODY}pt;
                min-height:    {sp.BTN_HEIGHT_MD}px;
            }}
            QPushButton:hover {{
                background: {c.BG_HOVER};
                border-color: {c.BORDER_STRONG};
                color: {c.TEXT_BRIGHT};
            }}
            QPushButton:pressed {{
                background: {c.BG_MAIN};
                border-color: {c.BLUE};
            }}
            QPushButton:disabled {{
                background: {c.BG_PANEL};
                color:      {c.TEXT_DISABLED};
                border-color: {c.BORDER_DIM};
            }}

            /* Semantic named buttons */
            QPushButton#startBtn {{
                background: {c.GREEN};
                color: {c.TEXT_INVERSE};
                border: none;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton#startBtn:hover   {{ background: {c.GREEN_BRIGHT}; }}
            QPushButton#startBtn:pressed {{ background: {c.GREEN}; border: 1px solid {c.GREEN_BRIGHT}; }}
            QPushButton#startBtn:disabled {{
                background: {c.BG_CARD};
                color: {c.TEXT_DISABLED};
                border: 1px solid {c.BORDER_DIM};
            }}

            QPushButton#stopBtn {{
                background: {c.RED};
                color: {c.TEXT_INVERSE};
                border: none;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton#stopBtn:hover   {{ background: {c.RED_BRIGHT}; }}
            QPushButton#stopBtn:pressed {{ background: {c.RED}; border: 1px solid {c.RED_BRIGHT}; }}
            QPushButton#stopBtn:disabled {{
                background: {c.BG_CARD};
                color: {c.TEXT_DISABLED};
                border: 1px solid {c.BORDER_DIM};
            }}

            QPushButton#strategyBtn {{
                background: {c.BLUE_DARK};
                color: {c.TEXT_INVERSE};
                border: none;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton#strategyBtn:hover   {{ background: {c.BLUE}; }}
            QPushButton#strategyBtn:pressed {{ background: {c.BLUE_DARK}; border: 1px solid {c.BLUE}; }}
            QPushButton#strategyBtn:disabled {{
                background: {c.BG_CARD};
                color: {c.TEXT_DISABLED};
                border: 1px solid {c.BORDER_DIM};
            }}

            QPushButton#callBtn {{
                background: {c.BLUE_DARK};
                color: {c.TEXT_INVERSE};
                border: none;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton#callBtn:hover   {{ background: {c.BLUE}; }}
            QPushButton#callBtn:disabled {{
                background: {c.BG_CARD};
                color: {c.TEXT_DISABLED};
                border: 1px solid {c.BORDER_DIM};
            }}

            QPushButton#putBtn {{
                background: {c.PURPLE_DARK};
                color: {c.TEXT_INVERSE};
                border: none;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton#putBtn:hover:enabled {{ background: {c.PURPLE}; }}
            QPushButton#putBtn:disabled {{
                background: {c.BG_CARD};
                color: {c.TEXT_DISABLED};
                border: 1px solid {c.BORDER_DIM};
            }}

            QPushButton#exitBtn {{
                background: {c.YELLOW};
                color: {c.TEXT_INVERSE};
                border: none;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton#exitBtn:hover:enabled {{ background: {c.YELLOW_BRIGHT}; }}
            QPushButton#exitBtn:disabled {{
                background: {c.BG_CARD};
                color: {c.TEXT_DISABLED};
                border: 1px solid {c.BORDER_DIM};
            }}

            QPushButton#connectionBtn {{
                background: {c.BG_CARD};
                color: {c.TEXT_DIM};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                font-weight: {ty.WEIGHT_MEDIUM};
            }}
            QPushButton#connectionBtnConnected {{
                background: {c.GREEN_GLOW};
                color: {c.GREEN};
                border: 1px solid {c.GREEN}44;
                font-weight: {ty.WEIGHT_SEMIBOLD};
            }}
            QPushButton#connectionBtnDisconnected {{
                background: {c.RED_GLOW};
                color: {c.RED};
                border: 1px solid {c.RED}44;
                font-weight: {ty.WEIGHT_SEMIBOLD};
            }}

            /* ── Progress bars ───────────────────────────────────────────────── */
            QProgressBar {{
                border:        {sp.SEPARATOR}px solid {c.BORDER_DIM};
                border-radius: {sp.RADIUS_MD}px;
                background:    {c.BG_CARD};
                text-align:    center;
                color:         {c.TEXT_MAIN};
                font-size:     {ty.SIZE_XS}pt;
                font-weight:   {ty.WEIGHT_SEMIBOLD};
                min-height:    {sp.PROGRESS_MD}px;
                max-height:    {sp.PROGRESS_LG}px;
            }}
            QProgressBar::chunk {{
                background:    qlineargradient(x1:0, y1:0, x2:1, y2:0,
                               stop:0 {c.BLUE_DARK}, stop:1 {c.BLUE});
                border-radius: {sp.RADIUS_MD}px;
            }}

            /* ── Labels ──────────────────────────────────────────────────────── */
            QLabel {{
                color:     {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                background: transparent;
            }}

            /* ── Splitter ────────────────────────────────────────────────────── */
            QSplitter::handle {{
                background: {c.BORDER_DIM};
            }}
            QSplitter::handle:horizontal {{ width:  {sp.SPLITTER}px; }}
            QSplitter::handle:vertical   {{ height: {sp.SPLITTER}px; }}
            QSplitter::handle:hover {{
                background: {c.BLUE};
            }}

            /* ── Checkboxes & Radio buttons ──────────────────────────────────── */
            QCheckBox, QRadioButton {{
                color:     {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                spacing:   {sp.GAP_SM}px;
                background: transparent;
            }}
            QCheckBox:disabled, QRadioButton:disabled {{
                color: {c.TEXT_DISABLED};
            }}
            QCheckBox::indicator {{
                width:  {sp.ICON_MD}px;
                height: {sp.ICON_MD}px;
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
                background: {c.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: {c.BLUE_DARK};
                border-color: {c.BLUE_DARK};
            }}
            QCheckBox::indicator:hover {{
                border-color: {c.BORDER_FOCUS};
            }}
            QRadioButton::indicator {{
                width:  {sp.ICON_MD}px;
                height: {sp.ICON_MD}px;
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.ICON_MD // 2}px;
                background: {c.BG_INPUT};
            }}
            QRadioButton::indicator:checked {{
                background: {c.BLUE_DARK};
                border-color: {c.BLUE_DARK};
            }}
            QRadioButton::indicator:hover {{
                border-color: {c.BORDER_FOCUS};
            }}

            /* ── Frames ──────────────────────────────────────────────────────── */
            QFrame[frameShape="4"],
            QFrame[frameShape="5"] {{
                color: {c.BORDER};
                background: {c.BORDER};
            }}

            /* ── List Widget ─────────────────────────────────────────────────── */
            QListWidget {{
                background:   {c.BG_PANEL};
                color:        {c.TEXT_MAIN};
                border:       {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                font-size:    {ty.SIZE_BODY}pt;
                outline: none;
            }}
            QListWidget::item {{
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                border-radius: {sp.RADIUS_SM}px;
                margin: 1px 2px;
            }}
            QListWidget::item:selected {{
                background: {c.BG_SELECTED};
                color: {c.TEXT_BRIGHT};
            }}
            QListWidget::item:hover {{
                background: {c.BG_HOVER};
            }}

            /* ── Tree Widget ─────────────────────────────────────────────────── */
            QTreeWidget {{
                background:   {c.BG_PANEL};
                color:        {c.TEXT_MAIN};
                border:       {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                font-size:    {ty.SIZE_BODY}pt;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                border-radius: {sp.RADIUS_SM}px;
            }}
            QTreeWidget::item:selected {{
                background: {c.BG_SELECTED};
                color: {c.TEXT_BRIGHT};
            }}
            QTreeWidget::item:hover {{
                background: {c.BG_HOVER};
            }}

            /* ── Dialog ──────────────────────────────────────────────────────── */
            QDialog {{
                background: {c.BG_MAIN};
                border-radius: {sp.RADIUS_LG}px;
            }}

            /* ── Dock Widget ─────────────────────────────────────────────────── */
            QDockWidget {{
                color:       {c.TEXT_MAIN};
                font-size:   {ty.SIZE_SM}pt;
                font-weight: {ty.WEIGHT_SEMIBOLD};
            }}
            QDockWidget::title {{
                background: {c.BG_CARD};
                border-bottom: {sp.SEPARATOR}px solid {c.BORDER};
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
            }}

            /* ── Tool Button ─────────────────────────────────────────────────── */
            QToolButton {{
                background:    {c.BG_CARD};
                color:         {c.TEXT_MAIN};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding:       {sp.PAD_SM}px {sp.PAD_MD}px;
                font-size:     {ty.SIZE_BODY}pt;
                min-height:    {sp.BTN_HEIGHT_SM}px;
            }}
            QToolButton:hover {{
                background: {c.BG_HOVER};
                border-color: {c.BORDER_STRONG};
            }}
            QToolButton:pressed {{
                background: {c.BG_MAIN};
            }}

            /* ── Wizard ──────────────────────────────────────────────────────── */
            QWizard {{
                background: {c.BG_MAIN};
            }}
            QWizardPage {{
                background: {c.BG_MAIN};
            }}

            /* ── MessageBox ──────────────────────────────────────────────────── */
            QMessageBox {{
                background: {c.BG_MAIN};
            }}
            QMessageBox QLabel {{
                color: {c.TEXT_MAIN};
                font-size: {ty.SIZE_BODY}pt;
                min-width: 300px;
            }}
        """

    # ── Convenience stylesheet snippets ───────────────────────────────────────

    def card_stylesheet(self,
                        radius_token: str = "RADIUS_LG",
                        bg_token: str = "BG_PANEL") -> str:
        c  = self._palette
        sp = self._spacing
        return f"""
            QFrame {{
                background:    {c.get(bg_token, c.BG_PANEL)};
                border:        {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.get(radius_token, sp.RADIUS_LG)}px;
                padding:       {sp.PAD_SM}px;
            }}
            QFrame:hover {{
                border-color: {c.BORDER_STRONG};
            }}
        """

    def label_stylesheet(self,
                         color_token: str = "TEXT_MAIN",
                         size_token:  str = "SIZE_BODY",
                         bold: bool = False) -> str:
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
                background: {c.BG_CARD};
                color:      {c.TEXT_DISABLED};
                border:     1px solid {c.BORDER_DIM};
            }}
        """

    def badge_stylesheet(self, color_token: str = "BLUE") -> str:
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
            f"letter-spacing: {ty.LETTER_CAPS};"
        )

    def log_stylesheet(self) -> str:
        c  = self._palette
        ty = self._typography
        sp = self._spacing
        return f"""
            QTextEdit, QPlainTextEdit {{
                background:  {c.BG_MAIN};
                color:       {c.TEXT_MAIN};
                border:      {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                font-family: {ty.FONT_MONO};
                font-size:   {ty.SIZE_MONO}pt;
                line-height: {ty.LINE_HEIGHT_LOG};
                padding:     {sp.PAD_SM}px;
                selection-background-color: {c.BG_SELECTED};
            }}
        """

    def pnl_progress_stylesheet(self, positive: bool = True) -> str:
        c  = self._palette
        sp = self._spacing
        chunk_color = c.GREEN if positive else c.RED
        glow_color  = c.GREEN_GLOW if positive else c.RED_GLOW
        return f"""
            QProgressBar {{
                border:        none;
                border-radius: {sp.RADIUS_MD}px;
                background:    {glow_color};
                text-align:    center;
            }}
            QProgressBar::chunk {{
                background:    qlineargradient(x1:0, y1:0, x2:1, y2:0,
                               stop:0 {chunk_color}cc, stop:1 {chunk_color});
                border-radius: {sp.RADIUS_MD}px;
            }}
        """

    def pnl_stat_chip_stylesheet(self) -> str:
        c  = self._palette
        ty = self._typography
        sp = self._spacing
        return (
            f"color: {c.TEXT_DIM}; "
            f"background: {c.BG_HOVER}; "
            f"border-radius: {sp.RADIUS_SM}px; "
            f"font-size: {ty.SIZE_XS}pt; "
            f"padding: 1px {sp.PAD_SM}px; "
            f"border: none;"
        )


# Module-level singleton — import this everywhere
theme_manager = ThemeManager()


def show_themed_message_box(parent, title, text, buttons=QMessageBox.Ok, icon=QMessageBox.NoIcon):
    """
    Show a message box with proper theme styling.
    """
    try:
        from gui.theme_manager import theme_manager

        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setStandardButtons(buttons)
        msg_box.setIcon(icon)

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
                background-color: {c.BG_CARD};
                color: {c.TEXT_MAIN};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_MD}px;
                padding: {sp.PAD_SM}px {sp.PAD_MD}px;
                min-width: 80px;
                font-size: {ty.SIZE_BODY}pt;
                font-weight: {ty.WEIGHT_SEMIBOLD};
            }}
            QPushButton:hover {{
                background-color: {c.BG_HOVER};
                border-color: {c.BORDER_FOCUS};
                color: {c.TEXT_BRIGHT};
            }}
            QPushButton:pressed {{
                background-color: {c.BG_MAIN};
            }}
            QMessageBox QPushButton[text="Yes"],
            QMessageBox QPushButton[text="OK"] {{
                background-color: {c.GREEN};
                color: {c.TEXT_INVERSE};
                border: none;
            }}
            QMessageBox QPushButton[text="Yes"]:hover,
            QMessageBox QPushButton[text="OK"]:hover {{
                background-color: {c.GREEN_BRIGHT};
            }}
            QMessageBox QPushButton[text="No"],
            QMessageBox QPushButton[text="Cancel"] {{
                background-color: {c.RED};
                color: {c.TEXT_INVERSE};
                border: none;
            }}
            QMessageBox QPushButton[text="No"]:hover,
            QMessageBox QPushButton[text="Cancel"]:hover {{
                background-color: {c.RED_BRIGHT};
            }}
        """)

        return msg_box.exec_()

    except Exception as e:
        logger.error(f"[show_themed_message_box] Failed: {e}", exc_info=True)
        return QMessageBox.question(parent, title, text, buttons)