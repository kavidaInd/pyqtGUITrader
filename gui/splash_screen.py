# gui/splash_screen.py
"""
Splash screen displayed during application startup.
Shows logo and loading status messages.
Fully integrated with ThemeManager for dynamic theming.
"""

import logging
import os
import time
from typing import Optional
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QPen, QBrush
from PyQt5.QtWidgets import QSplashScreen, QProgressBar, QLabel, QVBoxLayout, QWidget, QFrame, QApplication

from Utils.safe_getattr import safe_hasattr
# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


class AnimatedSplashScreen(QSplashScreen):
    """Enhanced splash screen with animated progress and status messages."""

    # Signal to update status message
    status_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, logo_path: Optional[str] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            # Create a custom pixmap for the splash screen
            sp = theme_manager.spacing
            self.width = 600
            self.height = 450  # Increased height to accommodate all elements with proper spacing

            # Create base pixmap
            pixmap = QPixmap(self.width, self.height)
            pixmap.fill(Qt.transparent)

            super().__init__(pixmap)

            # Store logo path with validation
            self.logo_path = logo_path
            if self.logo_path and not os.path.exists(self.logo_path):
                logger.warning(f"[AnimatedSplashScreen.__init__] Logo file not found: {self.logo_path}")
                self.logo_path = None

            # Current status and progress
            self.current_status = "Initializing..."
            self.current_progress = 0

            # Animation properties
            self.dot_count = 0
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._update_animation)
            self.animation_timer.start(500)  # Update every 500ms

            # Connect signals
            self.status_updated.connect(self._on_status_updated)
            self.progress_updated.connect(self._on_progress_updated)

            # Draw initial splash
            self.apply_theme()

            logger.info("[AnimatedSplashScreen.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.__init__] Failed: {e}", exc_info=True)
            # Ensure we still call super().__init__ even if construction fails
            if not safe_hasattr(self, '_is_initialized'):
                pixmap = QPixmap(600, 450)
                pixmap.fill(Qt.transparent)
                super().__init__(pixmap)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self.width = 600
            self.height = 450
            self.logo_path = None
            self.current_status = "Initializing..."
            self.current_progress = 0
            self.dot_count = 0
            self.animation_timer = None
            self._is_initialized = False
            self._closing = False
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._safe_defaults_init] Failed: {e}", exc_info=True)

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the splash screen.
        Called on theme change and initial render.
        """
        try:
            # Skip if closing
            if self._closing:
                return

            self._draw_splash()
            logger.debug("[AnimatedSplashScreen.apply_theme] Applied theme")
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.apply_theme] Failed: {e}", exc_info=True)

    def _draw_splash(self):
        """Draw the splash screen content using theme tokens."""
        try:
            # Skip if closing
            if self._closing:
                return

            c = self._c
            ty = self._ty
            sp = self._sp

            pixmap = QPixmap(self.width, self.height)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

            # Draw background gradient
            gradient = QLinearGradient(0, 0, self.width, self.height)
            gradient.setColorAt(0, QColor(c.BG_MAIN))
            gradient.setColorAt(1, QColor(c.BG_PANEL))

            painter.fillRect(0, 0, self.width, self.height, gradient)

            # Draw border
            painter.setPen(QColor(c.BORDER))
            painter.drawRect(0, 0, self.width - 1, self.height - 1)

            # Draw logo (if available)
            self._draw_logo(painter)

            # Draw application name
            font = QFont(ty.FONT_UI, ty.SIZE_2XL, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(c.TEXT_MAIN))
            painter.drawText(
                QRect(0, sp.PAD_XL * 15, self.width, sp.PAD_XL * 4),  # Adjusted y position
                Qt.AlignCenter,
                "Algo Trading Pro"
            )

            # Draw version
            font = QFont(ty.FONT_UI, ty.SIZE_SM)
            painter.setFont(font)
            painter.setPen(QColor(c.TEXT_DIM))
            painter.drawText(
                QRect(0, sp.PAD_XL * 18, self.width, sp.PAD_LG * 2),  # Adjusted y position
                Qt.AlignCenter,
                "Version 2.0.0"
            )

            # Draw status with animation
            font = QFont(ty.FONT_UI, ty.SIZE_BODY)
            painter.setFont(font)
            painter.setPen(QColor(c.BLUE))

            status_text = self.current_status + "." * self.dot_count
            painter.drawText(
                QRect(sp.PAD_XL * 4, sp.PAD_XL * 22, self.width - sp.PAD_XL * 8, sp.PAD_LG * 2),
                Qt.AlignCenter,
                status_text
            )

            # Draw progress bar background
            progress_x = sp.PAD_XL * 8
            progress_y = sp.PAD_XL * 25
            progress_width = self.width - sp.PAD_XL * 16
            progress_height = sp.PROGRESS_SM

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(c.BG_HOVER))
            painter.drawRoundedRect(
                progress_x, progress_y,
                progress_width, progress_height,
                sp.RADIUS_SM, sp.RADIUS_SM
            )

            # Draw progress fill
            if self.current_progress > 0:
                fill_width = int(progress_width * self.current_progress / 100)

                # Gradient fill
                progress_gradient = QLinearGradient(
                    progress_x, 0,
                    progress_x + fill_width, 0
                )
                progress_gradient.setColorAt(0, QColor(c.GREEN))
                progress_gradient.setColorAt(1, QColor(c.GREEN_BRIGHT))

                painter.setBrush(progress_gradient)
                painter.drawRoundedRect(
                    progress_x, progress_y,
                    fill_width, progress_height,
                    sp.RADIUS_SM, sp.RADIUS_SM
                )

            # Draw progress percentage
            font = QFont(ty.FONT_UI, ty.SIZE_XS)
            painter.setFont(font)
            painter.setPen(QColor(c.TEXT_DIM))
            painter.drawText(
                QRect(progress_x + progress_width + sp.PAD_MD, progress_y - sp.PAD_XS, sp.PAD_XL * 3, sp.PAD_LG),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{self.current_progress}%"
            )

            # Draw copyright - positioned at bottom with more space
            font = QFont(ty.FONT_UI, ty.SIZE_XS)
            painter.setFont(font)
            painter.setPen(QColor(c.TEXT_DISABLED))
            painter.drawText(
                QRect(0, self.height - sp.PAD_XL * 2, self.width, sp.PAD_LG),
                Qt.AlignCenter,
                "© 2025 Your Company. All rights reserved."
            )

            painter.end()

            self.setPixmap(pixmap)

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen._draw_splash] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._draw_splash] Failed: {e}", exc_info=True)

    def _draw_logo(self, painter: QPainter):
        """Draw the logo on the splash screen."""
        try:
            if not self.logo_path:
                self._draw_placeholder_logo(painter)
                return

            logo_pixmap = QPixmap(self.logo_path)
            if logo_pixmap.isNull():
                logger.warning(f"[AnimatedSplashScreen._draw_logo] Could not load logo from {self.logo_path}")
                self._draw_placeholder_logo(painter)
                return

            # Scale logo to fit (max 180x180)
            logo_pixmap = logo_pixmap.scaled(
                180, 180,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Center logo horizontally
            logo_x = (self.width - logo_pixmap.width()) // 2
            logo_y = self._sp.PAD_XL * 3  # 40px

            painter.drawPixmap(logo_x, logo_y, logo_pixmap)

        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._draw_logo] Failed: {e}", exc_info=True)
            self._draw_placeholder_logo(painter)

    def _draw_placeholder_logo(self, painter: QPainter):
        """Draw a placeholder logo when image not found."""
        try:
            c = self._c
            sp = self._sp

            # Draw circle
            painter.setPen(QPen(QColor(c.BLUE), 3))
            painter.setBrush(QColor(c.BG_MAIN))

            center_x = self.width // 2
            center_y = sp.PAD_XL * 8  # 110px
            radius = sp.PAD_XL * 4  # 50px

            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

            # Draw chart lines
            painter.setPen(QPen(QColor(c.GREEN_BRIGHT), 3))
            painter.drawLine(
                center_x - sp.PAD_XL * 2, center_y,
                center_x - sp.PAD_XL, center_y - sp.PAD_LG
            )
            painter.drawLine(
                center_x - sp.PAD_XL, center_y - sp.PAD_LG,
                center_x, center_y
            )
            painter.drawLine(
                center_x, center_y,
                center_x + sp.PAD_XL, center_y + sp.PAD_LG
            )
            painter.drawLine(
                center_x + sp.PAD_XL, center_y + sp.PAD_LG,
                center_x + sp.PAD_XL * 2, center_y
            )

        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._draw_placeholder_logo] Failed: {e}", exc_info=True)

    def _update_animation(self):
        """Update the animated dots."""
        try:
            # Skip if closing
            if self._closing:
                return

            self.dot_count = (self.dot_count + 1) % 4
            self._draw_splash()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen._update_animation] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._update_animation] Failed: {e}", exc_info=True)

    def _on_status_updated(self, status: str):
        """Handle status updates."""
        try:
            # Rule 6: Input validation
            if status is None:
                status = ""

            self.current_status = str(status)
            self._draw_splash()
            self.showMessage(status, Qt.AlignBottom | Qt.AlignCenter, QColor(self._c.BLUE))
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen._on_status_updated] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._on_status_updated] Failed: {e}", exc_info=True)

    def _on_progress_updated(self, progress: int):
        """Handle progress updates."""
        try:
            # Rule 6: Input validation and clamping
            progress = int(progress) if progress is not None else 0
            self.current_progress = max(0, min(100, progress))
            self._draw_splash()
        except (TypeError, ValueError) as e:
            logger.warning(f"[AnimatedSplashScreen._on_progress_updated] Invalid progress value: {e}")
            self.current_progress = 0
            self._draw_splash()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen._on_progress_updated] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._on_progress_updated] Failed: {e}", exc_info=True)

    def set_status(self, status: str):
        """Set the current status message."""
        try:
            # Rule 6: Input validation
            if status is None:
                status = ""
            self.status_updated.emit(str(status))
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.set_status] Failed: {e}", exc_info=True)

    def set_progress(self, progress: int):
        """Set the current progress percentage."""
        try:
            # Rule 6: Input validation
            progress = int(progress) if progress is not None else 0
            progress = max(0, min(100, progress))
            self.progress_updated.emit(progress)
        except (TypeError, ValueError) as e:
            logger.warning(f"[AnimatedSplashScreen.set_progress] Invalid progress value: {e}")
            self.progress_updated.emit(0)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.set_progress] Failed: {e}", exc_info=True)

    def finish_with_main_window(self, main_window):
        """Finish splash and show main window."""
        try:
            # Skip if closing
            if self._closing:
                return

            self.animation_timer.stop()

            # Ensure main window is shown and active
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()

            # Small delay to ensure window is visible before closing splash
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(200, self._safe_close)

        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.finish_with_main_window] Failed: {e}", exc_info=True)
            self._safe_close()

    def _safe_close(self):
        """Safely close the splash screen."""
        try:
            if not self._closing:
                self.close()
        except Exception as e:
            logger.warning(f"[AnimatedSplashScreen._safe_close] Failed: {e}")

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            # Prevent multiple cleanups
            if self._closing:
                return

            logger.info("[AnimatedSplashScreen.cleanup] Starting cleanup")
            self._closing = True

            if self.animation_timer and self.animation_timer.isActive():
                self.animation_timer.stop()
                self.animation_timer.timeout.disconnect(self._update_animation)
            self.animation_timer = None

            # Disconnect signals
            try:
                self.status_updated.disconnect(self._on_status_updated)
                self.progress_updated.disconnect(self._on_progress_updated)
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass  # Already disconnected or not connected

            logger.info("[AnimatedSplashScreen.cleanup] Cleanup completed")

        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen.closeEvent] RuntimeError: {e}", exc_info=True)
            event.accept()
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.closeEvent] Failed: {e}", exc_info=True)
            event.accept()


class SplashScreen(QWidget):
    """Standalone splash screen widget (alternative)."""

    def __init__(self, logo_path: Optional[str] = None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__()

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.logo_path = logo_path
            if self.logo_path and not os.path.exists(self.logo_path):
                logger.warning(f"[SplashScreen.__init__] Logo file not found: {self.logo_path}")
                self.logo_path = None

            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            # Size will be set in apply_theme
            self._center_on_screen()

            # Setup UI
            self._setup_ui()

            # Animation
            self.dot_count = 0
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._update_animation)
            self.animation_timer.start(500)

            # Apply theme
            self.apply_theme()

            logger.info("[SplashScreen.__init__] Initialized successfully")

        except Exception as e:
            logger.error(f"[SplashScreen.__init__] Failed: {e}", exc_info=True)
            super().__init__()

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        try:
            self.logo_path = None
            self.container = None
            self.logo_label = None
            self.status_label = None
            self.progress_bar = None
            self.progress_label = None
            self.dot_count = 0
            self.animation_timer = None
            self._closing = False
            self._is_initialized = False
        except Exception as e:
            logger.error(f"[SplashScreen._safe_defaults_init] Failed: {e}", exc_info=True)

    # =========================================================================
    # Shorthand properties for theme tokens
    # =========================================================================
    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the splash widget.
        Called on theme change and initial render.
        """
        try:
            # Skip if closing
            if self._closing:
                return

            c = self._c
            ty = self._ty
            sp = self._sp

            # Set fixed size using tokens
            self.setFixedSize(600, 450)

            # Update container style
            if self.container:
                self.container.setGeometry(0, 0, 600, 450)
                self.container.setStyleSheet(f"""
                    QFrame {{
                        background: qlineargradient(
                            x1: 0, y1: 0, x2: 1, y2: 1,
                            stop: 0 {c.BG_MAIN}, stop: 1 {c.BG_PANEL}
                        );
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_LG}px;
                    }}
                """)

            # Update logo label
            if self.logo_label:
                self._update_logo()

            # Update status label
            if self.status_label:
                self.status_label.setStyleSheet(f"""
                    font-size: {ty.SIZE_BODY}pt;
                    color: {c.BLUE};
                    margin-top: {sp.PAD_MD}px;
                    background: transparent;
                """)

            # Update progress bar
            if self.progress_bar:
                self.progress_bar.setFixedHeight(sp.PROGRESS_MD)
                self.progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: none;
                        background: {c.BG_HOVER};
                        border-radius: {sp.RADIUS_SM}px;
                        margin: {sp.PAD_XS}px {sp.PAD_XL}px;
                    }}
                    QProgressBar::chunk {{
                        background: qlineargradient(
                            x1: 0, y1: 0, x2: 1, y2: 0,
                            stop: 0 {c.GREEN}, stop: 1 {c.GREEN_BRIGHT}
                        );
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                """)

            # Update progress label
            if self.progress_label:
                self.progress_label.setStyleSheet(f"""
                    font-size: {ty.SIZE_XS}pt;
                    color: {c.TEXT_DIM};
                    margin-bottom: {sp.PAD_XS}px;
                    background: transparent;
                """)

            # Recenter after potential size change
            self._center_on_screen()

            logger.debug("[SplashScreen.apply_theme] Applied theme")

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[SplashScreen.apply_theme] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[SplashScreen.apply_theme] Failed: {e}", exc_info=True)

    def _center_on_screen(self):
        """Center the splash screen on the primary screen."""
        try:
            # Skip if closing
            if self._closing:
                return

            # Rule 11: Replace deprecated QDesktopWidget
            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.geometry()
                x = (screen_rect.width() - self.width()) // 2
                y = (screen_rect.height() - self.height()) // 2
                self.move(x, y)
        except Exception as e:
            logger.error(f"[SplashScreen._center_on_screen] Failed: {e}", exc_info=True)

    def _setup_ui(self):
        """Setup the splash screen UI."""
        try:
            c = self._c
            ty = self._ty
            sp = self._sp

            # Main container with gradient background
            self.container = QFrame(self)
            self.container.setGeometry(0, 0, 600, 450)

            # Layout
            layout = QVBoxLayout(self.container)
            layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
            layout.setSpacing(sp.GAP_MD)

            # Logo
            self.logo_label = QLabel()
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.logo_label.setFixedHeight(180)
            self._update_logo()

            layout.addWidget(self.logo_label)

            # App name
            app_name = QLabel("Algo Trading Pro")
            app_name.setAlignment(Qt.AlignCenter)
            app_name.setStyleSheet(f"""
                font-size: {ty.SIZE_2XL}pt;
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.TEXT_MAIN};
                background: transparent;
            """)
            layout.addWidget(app_name)

            # Version
            version = QLabel("Version 2.0.0")
            version.setAlignment(Qt.AlignCenter)
            version.setStyleSheet(f"""
                font-size: {ty.SIZE_SM}pt;
                color: {c.TEXT_DIM};
                background: transparent;
            """)
            layout.addWidget(version)

            layout.addStretch()

            # Status
            self.status_label = QLabel("Initializing...")
            self.status_label.setAlignment(Qt.AlignCenter)
            self.status_label.setStyleSheet(f"""
                font-size: {ty.SIZE_BODY}pt;
                color: {c.BLUE};
                margin-top: {sp.PAD_MD}px;
                background: transparent;
            """)
            layout.addWidget(self.status_label)

            # Progress bar
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(sp.PROGRESS_MD)
            self.progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    background: {c.BG_HOVER};
                    border-radius: {sp.RADIUS_SM}px;
                    margin: {sp.PAD_XS}px {sp.PAD_XL}px;
                }}
                QProgressBar::chunk {{
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 0,
                        stop: 0 {c.GREEN}, stop: 1 {c.GREEN_BRIGHT}
                    );
                    border-radius: {sp.RADIUS_SM}px;
                }}
            """)
            layout.addWidget(self.progress_bar)

            # Progress percentage
            self.progress_label = QLabel("0%")
            self.progress_label.setAlignment(Qt.AlignCenter)
            self.progress_label.setStyleSheet(f"""
                font-size: {ty.SIZE_XS}pt;
                color: {c.TEXT_DIM};
                margin-bottom: {sp.PAD_XS}px;
                background: transparent;
            """)
            layout.addWidget(self.progress_label)

            # Copyright - with proper spacing
            copyright = QLabel("© 2025 Your Company. All rights reserved.")
            copyright.setAlignment(Qt.AlignCenter)
            copyright.setStyleSheet(f"""
                font-size: {ty.SIZE_XS}pt;
                color: {c.TEXT_DISABLED};
                margin-top: {sp.PAD_MD}px;
                background: transparent;
            """)
            layout.addWidget(copyright)

        except Exception as e:
            logger.error(f"[SplashScreen._setup_ui] Failed: {e}", exc_info=True)

    def _update_logo(self):
        """Update the logo display."""
        try:
            if not self.logo_label:
                return

            c = self._c
            ty = self._ty

            # Try to load logo
            if self.logo_path:
                try:
                    logo_pixmap = QPixmap(self.logo_path)
                    if not logo_pixmap.isNull():
                        logo_pixmap = logo_pixmap.scaled(
                            180, 180,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        self.logo_label.setPixmap(logo_pixmap)
                        return
                except Exception as e:
                    logger.warning(f"[SplashScreen._update_logo] Failed to load logo: {e}")

            # Fallback to text logo
            self.logo_label.setText("📈")
            self.logo_label.setStyleSheet(f"""
                font-size: {ty.SIZE_DISPLAY * 3}pt;
                color: {c.BLUE};
                background: transparent;
            """)

        except Exception as e:
            logger.error(f"[SplashScreen._update_logo] Failed: {e}", exc_info=True)

    def _update_animation(self):
        """Update the animated dots."""
        try:
            # Skip if closing
            if self._closing or not self.status_label:
                return

            self.dot_count = (self.dot_count + 1) % 4
            dots = "." * self.dot_count
            base_text = self.status_label.text().rstrip(".")
            if "." in base_text:
                base_text = base_text[:base_text.rfind(".")]
            self.status_label.setText(base_text + dots)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[SplashScreen._update_animation] RuntimeError: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[SplashScreen._update_animation] Failed: {e}", exc_info=True)

    def set_status(self, status: str):
        """Set the current status message."""
        try:
            # Rule 6: Input validation
            if status is None:
                status = ""
            if self.status_label:
                self.status_label.setText(str(status))
        except Exception as e:
            logger.error(f"[SplashScreen.set_status] Failed: {e}", exc_info=True)

    def set_progress(self, progress: int):
        """Set the current progress percentage."""
        try:
            # Rule 6: Input validation and clamping
            progress = int(progress) if progress is not None else 0
            progress = max(0, min(100, progress))

            if self.progress_bar:
                self.progress_bar.setValue(progress)
            if self.progress_label:
                self.progress_label.setText(f"{progress}%")
        except (TypeError, ValueError) as e:
            logger.warning(f"[SplashScreen.set_progress] Invalid progress value: {e}")
        except Exception as e:
            logger.error(f"[SplashScreen.set_progress] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources - Rule 7"""
        try:
            # Prevent multiple cleanups
            if self._closing:
                return

            logger.info("[SplashScreen.cleanup] Starting cleanup")
            self._closing = True

            if self.animation_timer and self.animation_timer.isActive():
                self.animation_timer.stop()
                self.animation_timer.timeout.disconnect(self._update_animation)
            self.animation_timer = None

            # Disconnect signals
            try:
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass  # Already disconnected or not connected

            # Nullify widget references
            self.container = None
            self.logo_label = None
            self.status_label = None
            self.progress_bar = None
            self.progress_label = None

            logger.info("[SplashScreen.cleanup] Cleanup completed")

        except Exception as e:
            logger.error(f"[SplashScreen.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle close event - Rule 7"""
        try:
            self.cleanup()
            super().closeEvent(event)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[SplashScreen.closeEvent] RuntimeError: {e}", exc_info=True)
            event.accept()
        except Exception as e:
            logger.error(f"[SplashScreen.closeEvent] Failed: {e}", exc_info=True)
            event.accept()