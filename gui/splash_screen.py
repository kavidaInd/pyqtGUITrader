# gui/splash_screen.py
"""
Splash screen displayed during application startup.
Shows logo and loading status messages.
"""

import logging
import time
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QPen, QBrush
from PyQt5.QtWidgets import QSplashScreen, QProgressBar, QLabel, QVBoxLayout, QWidget, QFrame

logger = logging.getLogger(__name__)


class AnimatedSplashScreen(QSplashScreen):
    """Enhanced splash screen with animated progress and status messages."""

    # Signal to update status message
    status_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, logo_path=None):
        # Create a custom pixmap for the splash screen
        self.width = 600
        self.height = 450  # Increased height to accommodate all elements with proper spacing

        # Create base pixmap
        pixmap = QPixmap(self.width, self.height)
        pixmap.fill(Qt.transparent)

        super().__init__(pixmap)

        # Store logo path
        self.logo_path = logo_path or "resources/logo.png"  # Default path

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
        self._draw_splash()

        logger.info("Splash screen initialized")

    def _draw_splash(self):
        """Draw the splash screen content."""
        pixmap = QPixmap(self.width, self.height)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Draw background gradient
        gradient = QLinearGradient(0, 0, self.width, self.height)
        gradient.setColorAt(0, QColor(13, 17, 23))  # #0d1117
        gradient.setColorAt(1, QColor(22, 27, 34))  # #161b22

        painter.fillRect(0, 0, self.width, self.height, gradient)

        # Draw border
        painter.setPen(QColor(48, 54, 61))  # #30363d
        painter.drawRect(0, 0, self.width - 1, self.height - 1)

        # Draw logo (if available)
        try:
            logo_pixmap = QPixmap(self.logo_path)
            if not logo_pixmap.isNull():
                # Scale logo to fit (max 180x180 - slightly smaller)
                logo_pixmap = logo_pixmap.scaled(
                    180, 180,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # Center logo horizontally
                logo_x = (self.width - logo_pixmap.width()) // 2
                logo_y = 40  # Moved up a bit

                painter.drawPixmap(logo_x, logo_y, logo_pixmap)
            else:
                # Draw placeholder logo
                self._draw_placeholder_logo(painter)
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")
            self._draw_placeholder_logo(painter)

        # Draw application name
        font = QFont("Segoe UI", 24, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(230, 237, 243))  # #e6edf3
        painter.drawText(
            QRect(0, 200, self.width, 50),  # Adjusted y position
            Qt.AlignCenter,
            "Algo Trading Pro"
        )

        # Draw version
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.setPen(QColor(139, 148, 158))  # #8b949e
        painter.drawText(
            QRect(0, 240, self.width, 30),  # Adjusted y position
            Qt.AlignCenter,
            "Version 2.0.0"
        )

        # Draw status with animation
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        painter.setPen(QColor(88, 166, 255))  # #58a6ff

        status_text = self.current_status + "." * self.dot_count
        painter.drawText(
            QRect(50, 290, self.width - 100, 30),  # Adjusted y position
            Qt.AlignCenter,
            status_text
        )

        # Draw progress bar background
        progress_x = 100
        progress_y = 330  # Adjusted y position
        progress_width = self.width - 200
        progress_height = 8

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(33, 38, 45))  # #21262d
        painter.drawRoundedRect(
            progress_x, progress_y,
            progress_width, progress_height,
            4, 4
        )

        # Draw progress fill
        if self.current_progress > 0:
            fill_width = int(progress_width * self.current_progress / 100)

            # Gradient fill
            progress_gradient = QLinearGradient(
                progress_x, 0,
                progress_x + fill_width, 0
            )
            progress_gradient.setColorAt(0, QColor(35, 134, 54))  # #238636
            progress_gradient.setColorAt(1, QColor(46, 160, 67))  # #2ea043

            painter.setBrush(progress_gradient)
            painter.drawRoundedRect(
                progress_x, progress_y,
                fill_width, progress_height,
                4, 4
            )

        # Draw progress percentage
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.setPen(QColor(139, 148, 158))  # #8b949e
        painter.drawText(
            QRect(progress_x + progress_width + 10, progress_y - 5, 40, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{self.current_progress}%"
        )

        # Draw copyright - positioned at bottom with more space
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.setPen(QColor(110, 118, 129))  # #6e7681
        painter.drawText(
            QRect(0, self.height - 25, self.width, 20),  # Moved up slightly from bottom
            Qt.AlignCenter,
            "© 2025 Your Company. All rights reserved."
        )

        painter.end()

        self.setPixmap(pixmap)

    def _draw_placeholder_logo(self, painter):
        """Draw a placeholder logo when image not found."""
        # Draw circle
        painter.setPen(QPen(QColor(88, 166, 255), 3))  # #58a6ff
        painter.setBrush(QColor(13, 17, 23))  # #0d1117

        center_x = self.width // 2
        center_y = 110  # Adjusted y position
        radius = 50

        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

        # Draw chart lines
        painter.setPen(QPen(QColor(46, 160, 67), 3))  # #2ea043
        painter.drawLine(
            center_x - 30, center_y,
            center_x - 15, center_y - 15
        )
        painter.drawLine(
            center_x - 15, center_y - 15,
            center_x, center_y
        )
        painter.drawLine(
            center_x, center_y,
            center_x + 15, center_y + 15
        )
        painter.drawLine(
            center_x + 15, center_y + 15,
            center_x + 30, center_y
        )

    def _update_animation(self):
        """Update the animated dots."""
        self.dot_count = (self.dot_count + 1) % 4
        self._draw_splash()

    def _on_status_updated(self, status):
        """Handle status updates."""
        self.current_status = status
        self._draw_splash()
        self.showMessage(status, Qt.AlignBottom | Qt.AlignCenter, QColor(88, 166, 255))

    def _on_progress_updated(self, progress):
        """Handle progress updates."""
        self.current_progress = min(100, max(0, progress))
        self._draw_splash()

    def set_status(self, status):
        """Set the current status message."""
        self.status_updated.emit(status)

    def set_progress(self, progress):
        """Set the current progress percentage."""
        self.progress_updated.emit(progress)

    def finish_with_main_window(self, main_window):
        """Finish splash and show main window."""
        self.animation_timer.stop()

        # Ensure main window is shown and active
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

        # Small delay to ensure window is visible before closing splash
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(200, lambda: self.close())


class SplashScreen(QWidget):
    """Standalone splash screen widget (alternative)."""

    def __init__(self, logo_path=None):
        super().__init__()
        self.logo_path = logo_path or "resources/logo.png"
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(600, 450)  # Increased height

        # Center on screen
        self._center_on_screen()

        # Setup UI
        self._setup_ui()

        # Animation
        self.dot_count = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_timer.start(500)

        logger.info("Splash widget initialized")

    def _center_on_screen(self):
        """Center the splash screen on the primary screen."""
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _setup_ui(self):
        """Setup the splash screen UI."""
        # Main container with gradient background
        self.container = QFrame(self)
        self.container.setGeometry(0, 0, 600, 450)
        self.container.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #0d1117, stop: 1 #161b22
                );
                border: 1px solid #30363d;
                border-radius: 10px;
            }
        """)

        # Layout
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Logo
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedHeight(180)

        # Try to load logo
        try:
            logo_pixmap = QPixmap(self.logo_path)
            if not logo_pixmap.isNull():
                logo_pixmap = logo_pixmap.scaled(
                    180, 180,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.logo_label.setPixmap(logo_pixmap)
            else:
                self.logo_label.setText("📈")
                self.logo_label.setStyleSheet("font-size: 80px; color: #58a6ff;")
        except:
            self.logo_label.setText("📈")
            self.logo_label.setStyleSheet("font-size: 80px; color: #58a6ff;")

        layout.addWidget(self.logo_label)

        # App name
        app_name = QLabel("Algo Trading Pro")
        app_name.setAlignment(Qt.AlignCenter)
        app_name.setStyleSheet("font-size: 24px; font-weight: bold; color: #e6edf3;")
        layout.addWidget(app_name)

        # Version
        version = QLabel("Version 2.0.0")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("font-size: 10px; color: #8b949e;")
        layout.addWidget(version)

        layout.addStretch()

        # Status
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 11px; color: #58a6ff; margin-top: 10px;")
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background: #21262d;
                border-radius: 4px;
                margin: 5px 20px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #238636, stop: 1 #2ea043
                );
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Progress percentage
        self.progress_label = QLabel("0%")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 9px; color: #8b949e; margin-bottom: 5px;")
        layout.addWidget(self.progress_label)

        # Copyright - with proper spacing
        copyright = QLabel("© 2025 Your Company. All rights reserved.")
        copyright.setAlignment(Qt.AlignCenter)
        copyright.setStyleSheet("font-size: 8px; color: #6e7681; margin-top: 10px;")
        layout.addWidget(copyright)

    def _update_animation(self):
        """Update the animated dots."""
        self.dot_count = (self.dot_count + 1) % 4
        dots = "." * self.dot_count
        base_text = self.status_label.text().rstrip(".")
        if "." in base_text:
            base_text = base_text[:base_text.rfind(".")]
        self.status_label.setText(base_text + dots)

    def set_status(self, status):
        """Set the current status message."""
        self.status_label.setText(status)

    def set_progress(self, progress):
        """Set the current progress percentage."""
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"{progress}%")