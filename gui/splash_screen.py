"""
OptionPilot Splash Screen
Modern fintech style splash screen with animated loading status.

Features
--------
• Brand focused layout
• ThemeManager integration
• Smooth progress updates
• Animated loading dots
• Clean GPU friendly painting
"""

import os
import logging
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient
from PyQt5.QtWidgets import QSplashScreen

from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


class AnimatedSplashScreen(QSplashScreen):

    status_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, logo_path: Optional[str] = None):

        self.width = 720
        self.height = 460

        pixmap = QPixmap(self.width, self.height)
        pixmap.fill(Qt.transparent)

        super().__init__(pixmap)
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint)

        self.logo_path = logo_path if logo_path and os.path.exists(logo_path) else None

        self.current_status = "Initializing engine"
        self.current_progress = 0
        self.dot_count = 0

        theme_manager.theme_changed.connect(self.apply_theme)
        theme_manager.density_changed.connect(self.apply_theme)

        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animation)
        self.animation_timer.start(400)

        self.status_updated.connect(self._on_status)
        self.progress_updated.connect(self._on_progress)

        self.apply_theme()

    @property
    def c(self):
        return theme_manager.palette

    @property
    def ty(self):
        return theme_manager.typography

    def apply_theme(self, *_):
        self._draw()

    def _draw(self):

        pixmap = QPixmap(self.width, self.height)
        painter = QPainter(pixmap)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        c = self.c
        ty = self.ty

        # -------- Background Gradient --------

        bg = QLinearGradient(0, 0, 0, self.height)
        bg.setColorAt(0, QColor(c.BG_MAIN))
        bg.setColorAt(1, QColor(c.BG_PANEL))

        painter.fillRect(0, 0, self.width, self.height, bg)

        # -------- Logo --------

        center_x = self.width // 2
        logo_y = 110

        if self.logo_path:
            logo = QPixmap(self.logo_path)
            logo = logo.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            painter.drawPixmap(center_x - logo.width() // 2,
                               logo_y - logo.height() // 2,
                               logo)

        # -------- App Name --------

        title_font = QFont(ty.FONT_DISPLAY, ty.SIZE_DISPLAY, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(c.TEXT_BRIGHT))

        painter.drawText(
            0,
            logo_y + 90,
            self.width,
            50,
            Qt.AlignCenter,
            "OptionPilot"
        )

        # -------- Tagline --------

        tag_font = QFont(ty.FONT_UI, ty.SIZE_SM)
        painter.setFont(tag_font)
        painter.setPen(QColor(c.TEXT_MUTED))

        painter.drawText(
            0,
            logo_y + 130,
            self.width,
            30,
            Qt.AlignCenter,
            "Autopilot for Options Trading"
        )

        # -------- Divider --------

        painter.setPen(QColor(c.BORDER))
        painter.drawLine(200, logo_y + 170, self.width - 200, logo_y + 170)

        # -------- Status Text --------

        status = self.current_status + "." * self.dot_count

        status_font = QFont(ty.FONT_UI, ty.SIZE_BODY)
        painter.setFont(status_font)
        painter.setPen(QColor(c.BLUE))

        painter.drawText(
            0,
            logo_y + 210,
            self.width,
            40,
            Qt.AlignCenter,
            status
        )

        # -------- Progress Bar --------

        bar_width = 420
        bar_height = 8

        bar_x = (self.width - bar_width) // 2
        bar_y = logo_y + 260

        # Track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(c.BG_HOVER))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 4, 4)

        # Fill
        fill_width = int(bar_width * self.current_progress / 100)

        if fill_width > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + fill_width, 0)
            grad.setColorAt(0, QColor(c.GREEN))
            grad.setColorAt(1, QColor(c.GREEN_BRIGHT))

            painter.setBrush(grad)
            painter.drawRoundedRect(bar_x, bar_y, fill_width, bar_height, 4, 4)

        # -------- Percentage --------

        pct_font = QFont(ty.FONT_MONO, ty.SIZE_XS)
        painter.setFont(pct_font)
        painter.setPen(QColor(c.TEXT_MUTED))

        painter.drawText(
            0,
            bar_y + 20,
            self.width,
            20,
            Qt.AlignCenter,
            f"{self.current_progress}%"
        )

        # -------- Footer --------

        painter.setFont(QFont(ty.FONT_UI, ty.SIZE_XS))
        painter.setPen(QColor(c.TEXT_DISABLED))

        painter.drawText(
            0,
            self.height - 30,
            self.width,
            20,
            Qt.AlignCenter,
            "© 2025 OptionPilot • optionpilot.in"
        )

        painter.end()
        self.setPixmap(pixmap)

    def _update_animation(self):

        self.dot_count = (self.dot_count + 1) % 4
        self._draw()

    def _on_status(self, text: str):

        self.current_status = text
        self._draw()

    def _on_progress(self, value: int):

        self.current_progress = max(0, min(100, int(value)))
        self._draw()

    def set_status(self, text: str):

        self.status_updated.emit(text)

    def set_progress(self, value: int):

        self.progress_updated.emit(value)

    def finish_with_main_window(self, window):

        self.animation_timer.stop()

        window.show()
        window.raise_()
        window.activateWindow()

        QTimer.singleShot(200, self.close)