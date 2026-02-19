from tkinter import ttk
from typing import Dict


class TradingTheme:
    # Modern and vibrant color scheme - Fixed and improved
    COLORS: Dict[str, str] = {
        # Core background colors
        'bg_primary': '#0A1120',  # Dark navy for main background
        'bg_secondary': '#111827',  # Slightly lighter navy for cards
        'bg_tertiary': '#1F2937',  # Medium navy for elevated components
        'bg_elevated': '#374151',  # Light navy for floating elements

        # Primary accent colors
        'accent_primary': '#3B82F6',  # Bright blue
        'accent_secondary': '#60A5FA',  # Light blue
        'accent_success': '#10B981',  # Emerald green
        'accent_warning': '#F59E0B',  # Amber
        'accent_danger': '#EF4444',  # Red
        'accent_info': '#06B6D4',  # Cyan
        'accent_purple': '#8B5CF6',  # Purple

        # Text colors
        'text_primary': '#F3F4F6',  # Almost white
        'text_secondary': '#9CA3AF',  # Light gray
        'text_tertiary': '#6B7280',  # Medium gray
        'text_on_primary': '#FFFFFF',  # Pure white for buttons
        'text_on_dark': '#E5E7EB',  # Light gray for dark backgrounds

        # Status colors
        'status_success_bg': '#059669',  # Green
        'status_success_text': '#D1FAE5',
        'status_warning_bg': '#D97706',  # Amber
        'status_warning_text': '#FEF3C7',
        'status_danger_bg': '#DC2626',  # Red
        'status_danger_text': '#FEE2E2',

        # Disabled states
        'disabled_bg': '#374151',  # Muted background
        'disabled_text': '#6B7280',  # Medium gray (removed opacity)
        'disabled_border': '#4B5563',  # Muted border

        # Hover/Active states - Fixed
        'hover_primary': '#2563EB',  # Darker blue
        'hover_success': '#059669',  # Darker green
        'hover_warning': '#D97706',  # Darker amber
        'hover_danger': '#DC2626',  # Darker red

        # Active states (pressed)
        'active_primary': '#1D4ED8',  # Even darker blue
        'active_success': '#047857',  # Even darker green
        'active_warning': '#B45309',  # Even darker amber
        'active_danger': '#B91C1C',  # Even darker red

        # Gradients
        'gradient_start': '#3B82F6',  # Blue
        'gradient_end': '#2563EB',  # Darker blue

        # Chart colors
        'chart_line': '#60A5FA',  # Light blue
        'chart_grid': '#374151',  # Gray grid
        'chart_fill': '#3B82F620',  # Semi-transparent blue

        # Borders
        'border_light': '#374151',  # Light border
        'border_dark': '#1F2937',  # Dark border
        'border_focus': '#3B82F6',  # Focus border
    }

    @staticmethod
    def apply():
        """Apply the modern trading theme with improved button visibility"""
        style = ttk.Style()
        style.theme_use('clam')

        # Main application
        style.configure("Main.TFrame",
                        background=TradingTheme.COLORS['bg_primary'])

        # Cards
        style.configure("Card.TFrame",
                        background=TradingTheme.COLORS['bg_secondary'],
                        relief="solid",
                        borderwidth=1,
                        bordercolor=TradingTheme.COLORS['border_light'])

        # Headers
        style.configure("Header.TFrame",
                        background=TradingTheme.COLORS['bg_tertiary'])

        # Configure buttons with proper visibility
        TradingTheme._configure_buttons(style)

        # Configure labels
        TradingTheme._configure_labels(style)

        # Configure entry fields
        TradingTheme._configure_entries(style)

        # Configure notebook
        TradingTheme._configure_notebook(style)

    @staticmethod
    def _configure_buttons(style):
        """Configure all button styles with proper visibility"""

        # Primary button style
        style.configure("Primary.TButton",
                        padding=(15, 10),
                        background=TradingTheme.COLORS['accent_primary'],
                        foreground=TradingTheme.COLORS['text_on_primary'],
                        borderwidth=0,
                        relief="flat",
                        font=("Segoe UI", 9, "bold"))

        style.map("Primary.TButton",
                  background=[
                      ('active', TradingTheme.COLORS['hover_primary']),
                      ('pressed', TradingTheme.COLORS['active_primary']),
                      ('disabled', TradingTheme.COLORS['disabled_bg'])
                  ],
                  foreground=[
                      ('disabled', TradingTheme.COLORS['disabled_text'])
                  ])

        # Success button style
        style.configure("Success.TButton",
                        padding=(15, 10),
                        background=TradingTheme.COLORS['accent_success'],
                        foreground=TradingTheme.COLORS['text_on_primary'],
                        borderwidth=0,
                        relief="flat",
                        font=("Segoe UI", 9, "bold"))

        style.map("Success.TButton",
                  background=[
                      ('active', TradingTheme.COLORS['hover_success']),
                      ('pressed', TradingTheme.COLORS['active_success']),
                      ('disabled', TradingTheme.COLORS['disabled_bg'])
                  ],
                  foreground=[
                      ('disabled', TradingTheme.COLORS['disabled_text'])
                  ])

        # Warning button style
        style.configure("Warning.TButton",
                        padding=(15, 10),
                        background=TradingTheme.COLORS['accent_warning'],
                        foreground=TradingTheme.COLORS['text_on_primary'],
                        borderwidth=0,
                        relief="flat",
                        font=("Segoe UI", 9, "bold"))

        style.map("Warning.TButton",
                  background=[
                      ('active', TradingTheme.COLORS['hover_warning']),
                      ('pressed', TradingTheme.COLORS['active_warning']),
                      ('disabled', TradingTheme.COLORS['disabled_bg'])
                  ],
                  foreground=[
                      ('disabled', TradingTheme.COLORS['disabled_text'])
                  ])

        # Danger button style
        style.configure("Danger.TButton",
                        padding=(15, 10),
                        background=TradingTheme.COLORS['accent_danger'],
                        foreground=TradingTheme.COLORS['text_on_primary'],
                        borderwidth=0,
                        relief="flat",
                        font=("Segoe UI", 9, "bold"))

        style.map("Danger.TButton",
                  background=[
                      ('active', TradingTheme.COLORS['hover_danger']),
                      ('pressed', TradingTheme.COLORS['active_danger']),
                      ('disabled', TradingTheme.COLORS['disabled_bg'])
                  ],
                  foreground=[
                      ('disabled', TradingTheme.COLORS['disabled_text'])
                  ])

        # Secondary button style (for less prominent actions)
        style.configure("Secondary.TButton",
                        padding=(15, 10),
                        background=TradingTheme.COLORS['bg_elevated'],
                        foreground=TradingTheme.COLORS['text_primary'],
                        borderwidth=1,
                        relief="solid",
                        bordercolor=TradingTheme.COLORS['border_light'],
                        font=("Segoe UI", 9))

        style.map("Secondary.TButton",
                  background=[
                      ('active', TradingTheme.COLORS['bg_tertiary']),
                      ('pressed', TradingTheme.COLORS['bg_secondary']),
                      ('disabled', TradingTheme.COLORS['disabled_bg'])
                  ],
                  foreground=[
                      ('disabled', TradingTheme.COLORS['disabled_text'])
                  ],
                  bordercolor=[
                      ('active', TradingTheme.COLORS['accent_primary']),
                      ('disabled', TradingTheme.COLORS['disabled_border'])
                  ])

    @staticmethod
    def _configure_labels(style):
        """Configure label styles"""
        # Primary labels
        style.configure("Primary.TLabel",
                        background=TradingTheme.COLORS['bg_secondary'],
                        foreground=TradingTheme.COLORS['text_primary'],
                        font=("Segoe UI", 10))

        # Header labels
        style.configure("Header.TLabel",
                        background=TradingTheme.COLORS['bg_tertiary'],
                        foreground=TradingTheme.COLORS['text_primary'],
                        font=("Segoe UI", 14, "bold"))

        # Status labels
        style.configure("Status.Success.TLabel",
                        background=TradingTheme.COLORS['status_success_bg'],
                        foreground=TradingTheme.COLORS['status_success_text'],
                        padding=(10, 5),
                        font=("Segoe UI", 9, "bold"))

        style.configure("Status.Warning.TLabel",
                        background=TradingTheme.COLORS['status_warning_bg'],
                        foreground=TradingTheme.COLORS['status_warning_text'],
                        padding=(10, 5),
                        font=("Segoe UI", 9, "bold"))

        style.configure("Status.Danger.TLabel",
                        background=TradingTheme.COLORS['status_danger_bg'],
                        foreground=TradingTheme.COLORS['status_danger_text'],
                        padding=(10, 5),
                        font=("Segoe UI", 9, "bold"))

        # Manual trading section labels
        style.configure("Manual.TFrame",
                        background=TradingTheme.COLORS['bg_tertiary'])

        style.configure("Manual.Disabled.TFrame",
                        background=TradingTheme.COLORS['disabled_bg'])

        style.configure("Manual.Header.TLabel",
                        background=TradingTheme.COLORS['bg_tertiary'],
                        foreground=TradingTheme.COLORS['text_primary'],
                        font=("Segoe UI", 11, "bold"))

        style.configure("Manual.Disabled.TLabel",
                        background=TradingTheme.COLORS['disabled_bg'],
                        foreground=TradingTheme.COLORS['disabled_text'])

    @staticmethod
    def _configure_entries(style):
        """Configure entry field styles"""
        style.configure("Trading.TEntry",
                        fieldbackground=TradingTheme.COLORS['bg_tertiary'],
                        foreground=TradingTheme.COLORS['text_primary'],
                        insertcolor=TradingTheme.COLORS['text_primary'],
                        borderwidth=1,
                        relief="solid",
                        bordercolor=TradingTheme.COLORS['border_light'],
                        font=("Segoe UI", 10))

        style.map("Trading.TEntry",
                  fieldbackground=[
                      ('disabled', TradingTheme.COLORS['disabled_bg']),
                      ('focus', TradingTheme.COLORS['bg_elevated'])
                  ],
                  foreground=[
                      ('disabled', TradingTheme.COLORS['disabled_text'])
                  ],
                  bordercolor=[
                      ('focus', TradingTheme.COLORS['border_focus']),
                      ('disabled', TradingTheme.COLORS['disabled_border'])
                  ])

    @staticmethod
    def _configure_notebook(style):
        """Configure notebook/tab styles"""
        style.configure("Trading.TNotebook",
                        background=TradingTheme.COLORS['bg_primary'],
                        borderwidth=0)

        style.configure("Trading.TNotebook.Tab",
                        padding=(5, 8),
                        background=TradingTheme.COLORS['bg_tertiary'],
                        foreground=TradingTheme.COLORS['text_secondary'],
                        borderwidth=0,
                        font=("Segoe UI", 10))

        style.map("Trading.TNotebook.Tab",
                  background=[
                      ('selected', TradingTheme.COLORS['bg_elevated']),
                      ('active', TradingTheme.COLORS['bg_secondary'])
                  ],
                  foreground=[
                      ('selected', TradingTheme.COLORS['text_primary']),
                      ('active', TradingTheme.COLORS['text_primary'])
                  ])

    @classmethod
    def get_status_colors(cls) -> dict:
        """Get status-specific colors"""
        return {
            'active': cls.COLORS['accent_success'],
            'warning': cls.COLORS['accent_warning'],
            'error': cls.COLORS['accent_danger'],
            'inactive': cls.COLORS['text_tertiary']
        }

    @classmethod
    def get_indicator_colors(cls) -> dict:
        """Get indicator-specific colors"""
        return {
            'online': cls.COLORS['accent_success'],
            'offline': cls.COLORS['accent_danger'],
            'warning': cls.COLORS['accent_warning'],
            'neutral': cls.COLORS['text_tertiary']
        }

    @classmethod
    def get_chart_colors(cls) -> dict:
        """Get chart-specific colors"""
        return {
            'line': cls.COLORS['chart_line'],
            'grid': cls.COLORS['chart_grid'],
            'fill': cls.COLORS['chart_fill'],
            'positive': cls.COLORS['accent_success'],
            'negative': cls.COLORS['accent_danger'],
            'neutral': cls.COLORS['text_secondary']
        }


def apply_modern_styles():
    """Apply the modern trading theme"""
    TradingTheme.apply()