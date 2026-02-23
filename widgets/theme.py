from tkinter import ttk
import logging
import logging.handlers
import traceback
from typing import Dict, Optional, Any

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


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
        try:
            style = ttk.Style()
            style.theme_use('clam')

            # Main application
            try:
                style.configure("Main.TFrame",
                                background=TradingTheme.COLORS.get('bg_primary', '#0A1120'))
            except Exception as e:
                logger.error(f"Failed to configure Main.TFrame: {e}", exc_info=True)

            # Cards
            try:
                style.configure("Card.TFrame",
                                background=TradingTheme.COLORS.get('bg_secondary', '#111827'),
                                relief="solid",
                                borderwidth=1,
                                bordercolor=TradingTheme.COLORS.get('border_light', '#374151'))
            except Exception as e:
                logger.error(f"Failed to configure Card.TFrame: {e}", exc_info=True)

            # Headers
            try:
                style.configure("Header.TFrame",
                                background=TradingTheme.COLORS.get('bg_tertiary', '#1F2937'))
            except Exception as e:
                logger.error(f"Failed to configure Header.TFrame: {e}", exc_info=True)

            # Configure buttons with proper visibility
            TradingTheme._configure_buttons(style)

            # Configure labels
            TradingTheme._configure_labels(style)

            # Configure entry fields
            TradingTheme._configure_entries(style)

            # Configure notebook
            TradingTheme._configure_notebook(style)

            logger.info("Trading theme applied successfully")

        except Exception as e:
            logger.error(f"[TradingTheme.apply] Failed: {e}", exc_info=True)

    @staticmethod
    def _configure_buttons(style):
        """Configure all button styles with proper visibility"""
        try:
            # Primary button style
            try:
                style.configure("Primary.TButton",
                                padding=(15, 10),
                                background=TradingTheme.COLORS.get('accent_primary', '#3B82F6'),
                                foreground=TradingTheme.COLORS.get('text_on_primary', '#FFFFFF'),
                                borderwidth=0,
                                relief="flat",
                                font=("Segoe UI", 9, "bold"))

                style.map("Primary.TButton",
                          background=[
                              ('active', TradingTheme.COLORS.get('hover_primary', '#2563EB')),
                              ('pressed', TradingTheme.COLORS.get('active_primary', '#1D4ED8')),
                              ('disabled', TradingTheme.COLORS.get('disabled_bg', '#374151'))
                          ],
                          foreground=[
                              ('disabled', TradingTheme.COLORS.get('disabled_text', '#6B7280'))
                          ])
            except Exception as e:
                logger.error(f"Failed to configure Primary.TButton: {e}", exc_info=True)

            # Success button style
            try:
                style.configure("Success.TButton",
                                padding=(15, 10),
                                background=TradingTheme.COLORS.get('accent_success', '#10B981'),
                                foreground=TradingTheme.COLORS.get('text_on_primary', '#FFFFFF'),
                                borderwidth=0,
                                relief="flat",
                                font=("Segoe UI", 9, "bold"))

                style.map("Success.TButton",
                          background=[
                              ('active', TradingTheme.COLORS.get('hover_success', '#059669')),
                              ('pressed', TradingTheme.COLORS.get('active_success', '#047857')),
                              ('disabled', TradingTheme.COLORS.get('disabled_bg', '#374151'))
                          ],
                          foreground=[
                              ('disabled', TradingTheme.COLORS.get('disabled_text', '#6B7280'))
                          ])
            except Exception as e:
                logger.error(f"Failed to configure Success.TButton: {e}", exc_info=True)

            # Warning button style
            try:
                style.configure("Warning.TButton",
                                padding=(15, 10),
                                background=TradingTheme.COLORS.get('accent_warning', '#F59E0B'),
                                foreground=TradingTheme.COLORS.get('text_on_primary', '#FFFFFF'),
                                borderwidth=0,
                                relief="flat",
                                font=("Segoe UI", 9, "bold"))

                style.map("Warning.TButton",
                          background=[
                              ('active', TradingTheme.COLORS.get('hover_warning', '#D97706')),
                              ('pressed', TradingTheme.COLORS.get('active_warning', '#B45309')),
                              ('disabled', TradingTheme.COLORS.get('disabled_bg', '#374151'))
                          ],
                          foreground=[
                              ('disabled', TradingTheme.COLORS.get('disabled_text', '#6B7280'))
                          ])
            except Exception as e:
                logger.error(f"Failed to configure Warning.TButton: {e}", exc_info=True)

            # Danger button style
            try:
                style.configure("Danger.TButton",
                                padding=(15, 10),
                                background=TradingTheme.COLORS.get('accent_danger', '#EF4444'),
                                foreground=TradingTheme.COLORS.get('text_on_primary', '#FFFFFF'),
                                borderwidth=0,
                                relief="flat",
                                font=("Segoe UI", 9, "bold"))

                style.map("Danger.TButton",
                          background=[
                              ('active', TradingTheme.COLORS.get('hover_danger', '#DC2626')),
                              ('pressed', TradingTheme.COLORS.get('active_danger', '#B91C1C')),
                              ('disabled', TradingTheme.COLORS.get('disabled_bg', '#374151'))
                          ],
                          foreground=[
                              ('disabled', TradingTheme.COLORS.get('disabled_text', '#6B7280'))
                          ])
            except Exception as e:
                logger.error(f"Failed to configure Danger.TButton: {e}", exc_info=True)

            # Secondary button style (for less prominent actions)
            try:
                style.configure("Secondary.TButton",
                                padding=(15, 10),
                                background=TradingTheme.COLORS.get('bg_elevated', '#374151'),
                                foreground=TradingTheme.COLORS.get('text_primary', '#F3F4F6'),
                                borderwidth=1,
                                relief="solid",
                                bordercolor=TradingTheme.COLORS.get('border_light', '#374151'),
                                font=("Segoe UI", 9))

                style.map("Secondary.TButton",
                          background=[
                              ('active', TradingTheme.COLORS.get('bg_tertiary', '#1F2937')),
                              ('pressed', TradingTheme.COLORS.get('bg_secondary', '#111827')),
                              ('disabled', TradingTheme.COLORS.get('disabled_bg', '#374151'))
                          ],
                          foreground=[
                              ('disabled', TradingTheme.COLORS.get('disabled_text', '#6B7280'))
                          ],
                          bordercolor=[
                              ('active', TradingTheme.COLORS.get('accent_primary', '#3B82F6')),
                              ('disabled', TradingTheme.COLORS.get('disabled_border', '#4B5563'))
                          ])
            except Exception as e:
                logger.error(f"Failed to configure Secondary.TButton: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[_configure_buttons] Failed: {e}", exc_info=True)

    @staticmethod
    def _configure_labels(style):
        """Configure label styles"""
        try:
            # Primary labels
            try:
                style.configure("Primary.TLabel",
                                background=TradingTheme.COLORS.get('bg_secondary', '#111827'),
                                foreground=TradingTheme.COLORS.get('text_primary', '#F3F4F6'),
                                font=("Segoe UI", 10))
            except Exception as e:
                logger.error(f"Failed to configure Primary.TLabel: {e}", exc_info=True)

            # Header labels
            try:
                style.configure("Header.TLabel",
                                background=TradingTheme.COLORS.get('bg_tertiary', '#1F2937'),
                                foreground=TradingTheme.COLORS.get('text_primary', '#F3F4F6'),
                                font=("Segoe UI", 14, "bold"))
            except Exception as e:
                logger.error(f"Failed to configure Header.TLabel: {e}", exc_info=True)

            # Status labels
            try:
                style.configure("Status.Success.TLabel",
                                background=TradingTheme.COLORS.get('status_success_bg', '#059669'),
                                foreground=TradingTheme.COLORS.get('status_success_text', '#D1FAE5'),
                                padding=(10, 5),
                                font=("Segoe UI", 9, "bold"))
            except Exception as e:
                logger.error(f"Failed to configure Status.Success.TLabel: {e}", exc_info=True)

            try:
                style.configure("Status.Warning.TLabel",
                                background=TradingTheme.COLORS.get('status_warning_bg', '#D97706'),
                                foreground=TradingTheme.COLORS.get('status_warning_text', '#FEF3C7'),
                                padding=(10, 5),
                                font=("Segoe UI", 9, "bold"))
            except Exception as e:
                logger.error(f"Failed to configure Status.Warning.TLabel: {e}", exc_info=True)

            try:
                style.configure("Status.Danger.TLabel",
                                background=TradingTheme.COLORS.get('status_danger_bg', '#DC2626'),
                                foreground=TradingTheme.COLORS.get('status_danger_text', '#FEE2E2'),
                                padding=(10, 5),
                                font=("Segoe UI", 9, "bold"))
            except Exception as e:
                logger.error(f"Failed to configure Status.Danger.TLabel: {e}", exc_info=True)

            # Manual trading section labels
            try:
                style.configure("Manual.TFrame",
                                background=TradingTheme.COLORS.get('bg_tertiary', '#1F2937'))
            except Exception as e:
                logger.error(f"Failed to configure Manual.TFrame: {e}", exc_info=True)

            try:
                style.configure("Manual.Disabled.TFrame",
                                background=TradingTheme.COLORS.get('disabled_bg', '#374151'))
            except Exception as e:
                logger.error(f"Failed to configure Manual.Disabled.TFrame: {e}", exc_info=True)

            try:
                style.configure("Manual.Header.TLabel",
                                background=TradingTheme.COLORS.get('bg_tertiary', '#1F2937'),
                                foreground=TradingTheme.COLORS.get('text_primary', '#F3F4F6'),
                                font=("Segoe UI", 11, "bold"))
            except Exception as e:
                logger.error(f"Failed to configure Manual.Header.TLabel: {e}", exc_info=True)

            try:
                style.configure("Manual.Disabled.TLabel",
                                background=TradingTheme.COLORS.get('disabled_bg', '#374151'),
                                foreground=TradingTheme.COLORS.get('disabled_text', '#6B7280'))
            except Exception as e:
                logger.error(f"Failed to configure Manual.Disabled.TLabel: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[_configure_labels] Failed: {e}", exc_info=True)

    @staticmethod
    def _configure_entries(style):
        """Configure entry field styles"""
        try:
            style.configure("Trading.TEntry",
                            fieldbackground=TradingTheme.COLORS.get('bg_tertiary', '#1F2937'),
                            foreground=TradingTheme.COLORS.get('text_primary', '#F3F4F6'),
                            insertcolor=TradingTheme.COLORS.get('text_primary', '#F3F4F6'),
                            borderwidth=1,
                            relief="solid",
                            bordercolor=TradingTheme.COLORS.get('border_light', '#374151'),
                            font=("Segoe UI", 10))

            style.map("Trading.TEntry",
                      fieldbackground=[
                          ('disabled', TradingTheme.COLORS.get('disabled_bg', '#374151')),
                          ('focus', TradingTheme.COLORS.get('bg_elevated', '#374151'))
                      ],
                      foreground=[
                          ('disabled', TradingTheme.COLORS.get('disabled_text', '#6B7280'))
                      ],
                      bordercolor=[
                          ('focus', TradingTheme.COLORS.get('border_focus', '#3B82F6')),
                          ('disabled', TradingTheme.COLORS.get('disabled_border', '#4B5563'))
                      ])
        except Exception as e:
            logger.error(f"[_configure_entries] Failed: {e}", exc_info=True)

    @staticmethod
    def _configure_notebook(style):
        """Configure notebook/tab styles"""
        try:
            style.configure("Trading.TNotebook",
                            background=TradingTheme.COLORS.get('bg_primary', '#0A1120'),
                            borderwidth=0)

            style.configure("Trading.TNotebook.Tab",
                            padding=(5, 8),
                            background=TradingTheme.COLORS.get('bg_tertiary', '#1F2937'),
                            foreground=TradingTheme.COLORS.get('text_secondary', '#9CA3AF'),
                            borderwidth=0,
                            font=("Segoe UI", 10))

            style.map("Trading.TNotebook.Tab",
                      background=[
                          ('selected', TradingTheme.COLORS.get('bg_elevated', '#374151')),
                          ('active', TradingTheme.COLORS.get('bg_secondary', '#111827'))
                      ],
                      foreground=[
                          ('selected', TradingTheme.COLORS.get('text_primary', '#F3F4F6')),
                          ('active', TradingTheme.COLORS.get('text_primary', '#F3F4F6'))
                      ])
        except Exception as e:
            logger.error(f"[_configure_notebook] Failed: {e}", exc_info=True)

    @classmethod
    def get_status_colors(cls) -> dict:
        """Get status-specific colors"""
        try:
            return {
                'active': cls.COLORS.get('accent_success', '#10B981'),
                'warning': cls.COLORS.get('accent_warning', '#F59E0B'),
                'error': cls.COLORS.get('accent_danger', '#EF4444'),
                'inactive': cls.COLORS.get('text_tertiary', '#6B7280')
            }
        except Exception as e:
            logger.error(f"[get_status_colors] Failed: {e}", exc_info=True)
            return {
                'active': '#10B981',
                'warning': '#F59E0B',
                'error': '#EF4444',
                'inactive': '#6B7280'
            }

    @classmethod
    def get_indicator_colors(cls) -> dict:
        """Get indicator-specific colors"""
        try:
            return {
                'online': cls.COLORS.get('accent_success', '#10B981'),
                'offline': cls.COLORS.get('accent_danger', '#EF4444'),
                'warning': cls.COLORS.get('accent_warning', '#F59E0B'),
                'neutral': cls.COLORS.get('text_tertiary', '#6B7280')
            }
        except Exception as e:
            logger.error(f"[get_indicator_colors] Failed: {e}", exc_info=True)
            return {
                'online': '#10B981',
                'offline': '#EF4444',
                'warning': '#F59E0B',
                'neutral': '#6B7280'
            }

    @classmethod
    def get_chart_colors(cls) -> dict:
        """Get chart-specific colors"""
        try:
            return {
                'line': cls.COLORS.get('chart_line', '#60A5FA'),
                'grid': cls.COLORS.get('chart_grid', '#374151'),
                'fill': cls.COLORS.get('chart_fill', '#3B82F620'),
                'positive': cls.COLORS.get('accent_success', '#10B981'),
                'negative': cls.COLORS.get('accent_danger', '#EF4444'),
                'neutral': cls.COLORS.get('text_secondary', '#9CA3AF')
            }
        except Exception as e:
            logger.error(f"[get_chart_colors] Failed: {e}", exc_info=True)
            return {
                'line': '#60A5FA',
                'grid': '#374151',
                'fill': '#3B82F620',
                'positive': '#10B981',
                'negative': '#EF4444',
                'neutral': '#9CA3AF'
            }

    # Rule 8: Cleanup method
    @classmethod
    def cleanup(cls):
        """Clean up resources (minimal for this class)"""
        try:
            logger.info("[TradingTheme] Cleanup completed")
        except Exception as e:
            logger.error(f"[TradingTheme.cleanup] Error: {e}", exc_info=True)


def apply_modern_styles():
    """Apply the modern trading theme"""
    try:
        TradingTheme.apply()
    except Exception as e:
        logger.error(f"[apply_modern_styles] Failed: {e}", exc_info=True)