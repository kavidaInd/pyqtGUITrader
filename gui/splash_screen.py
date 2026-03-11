# gui/splash_screen.py
"""
Splash screen displayed during application startup.
Shows logo and loading status messages.
Fully integrated with ThemeManager for dynamic theming.
"""

import logging
import math
import os
import time
from typing import Optional
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect, QPoint, QPointF
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QFont, QLinearGradient, QPen,
    QBrush, QRadialGradient, QConicalGradient, QPainterPath
)
from PyQt5.QtWidgets import (
    QSplashScreen, QProgressBar, QLabel, QVBoxLayout,
    QWidget, QFrame, QApplication
)

from Utils.safe_getattr import safe_hasattr
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


class AnimatedSplashScreen(QSplashScreen):
    """Enhanced splash screen with animated progress and status messages."""

    status_updated   = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, logo_path: Optional[str] = None):
        self._safe_defaults_init()

        try:
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.width  = 640
            self.height = 420

            pixmap = QPixmap(self.width, self.height)
            pixmap.fill(Qt.transparent)

            super().__init__(pixmap)
            self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint)

            self.logo_path = logo_path
            if self.logo_path and not os.path.exists(self.logo_path):
                logger.warning(f"[AnimatedSplashScreen] Logo not found: {self.logo_path}")
                self.logo_path = None

            self.current_status   = "Initializing..."
            self.current_progress = 0
            self.dot_count        = 0
            self._tick_count      = 0

            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._update_animation)
            self.animation_timer.start(400)

            self.status_updated.connect(self._on_status_updated)
            self.progress_updated.connect(self._on_progress_updated)

            self.apply_theme()
            logger.info("[AnimatedSplashScreen] Initialized")

        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.__init__] Failed: {e}", exc_info=True)
            if not safe_hasattr(self, '_is_initialized'):
                pixmap = QPixmap(640, 420)
                pixmap.fill(Qt.transparent)
                super().__init__(pixmap)

    def _safe_defaults_init(self):
        try:
            self.width            = 640
            self.height           = 420
            self.logo_path        = None
            self.current_status   = "Initializing..."
            self.current_progress = 0
            self.dot_count        = 0
            self.animation_timer  = None
            self._is_initialized  = False
            self._closing         = False
            self._tick_count      = 0
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._safe_defaults_init] {e}", exc_info=True)

    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        try:
            if self._closing:
                return
            self._draw_splash()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            else:
                logger.error(f"[AnimatedSplashScreen.apply_theme] {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.apply_theme] {e}", exc_info=True)

    def _draw_splash(self):
        try:
            if self._closing:
                return

            c  = self._c
            ty = self._ty
            sp = self._sp

            pixmap = QPixmap(self.width, self.height)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

            # ── Background: deep gradient ──────────────────────────────────
            bg_grad = QLinearGradient(0, 0, self.width, self.height)
            bg_grad.setColorAt(0.0, QColor(c.BG_MAIN))
            bg_grad.setColorAt(0.5, QColor(c.BG_PANEL))
            bg_grad.setColorAt(1.0, QColor(c.BG_CARD))
            painter.fillRect(0, 0, self.width, self.height, bg_grad)

            # ── Subtle radial glow top-center ──────────────────────────────
            glow = QRadialGradient(self.width // 2, 60, 180)
            glow.setColorAt(0.0, QColor(c.BLUE_DARK + "30"))
            glow.setColorAt(1.0, QColor(c.BG_MAIN + "00"))
            painter.fillRect(0, 0, self.width, 200, glow)

            # ── Border with subtle glow ────────────────────────────────────
            border_pen = QPen(QColor(c.BORDER))
            border_pen.setWidth(1)
            painter.setPen(border_pen)
            path = QPainterPath()
            path.addRoundedRect(1, 1, self.width - 2, self.height - 2, 12, 12)
            painter.drawPath(path)

            # Thin inner highlight line at top
            highlight_grad = QLinearGradient(0, 1, self.width, 1)
            highlight_grad.setColorAt(0.0, QColor(c.BLUE + "00"))
            highlight_grad.setColorAt(0.3, QColor(c.BLUE + "60"))
            highlight_grad.setColorAt(0.7, QColor(c.BLUE + "60"))
            highlight_grad.setColorAt(1.0, QColor(c.BLUE + "00"))
            painter.setPen(QPen(QBrush(highlight_grad), 1.5))
            painter.drawLine(12, 1, self.width - 12, 1)

            # ── Logo area ─────────────────────────────────────────────────
            logo_center_y = 100
            self._draw_logo_area(painter, logo_center_y, c, ty, sp)

            # ── App name ──────────────────────────────────────────────────
            title_y = 168
            name_font = QFont(ty.FONT_UI, ty.SIZE_3XL, QFont.Bold)
            painter.setFont(name_font)

            # Title shadow
            painter.setPen(QColor(c.BG_MAIN + "cc"))
            painter.drawText(QRect(1, title_y + 1, self.width, 40), Qt.AlignCenter, "Algo Trading Pro")

            # Title gradient
            title_grad = QLinearGradient(0, title_y, 0, title_y + 40)
            title_grad.setColorAt(0.0, QColor(c.TEXT_BRIGHT))
            title_grad.setColorAt(1.0, QColor(c.TEXT_MAIN))
            painter.setPen(QPen(QBrush(title_grad), 1))
            painter.drawText(QRect(0, title_y, self.width, 40), Qt.AlignCenter, "Algo Trading Pro")

            # ── Subtitle / version ─────────────────────────────────────────
            sub_font = QFont(ty.FONT_UI, ty.SIZE_SM)
            painter.setFont(sub_font)
            painter.setPen(QColor(c.TEXT_MUTED))
            painter.drawText(
                QRect(0, title_y + 44, self.width, 20),
                Qt.AlignCenter,
                "Professional Algorithmic Trading Platform  ·  v2.0"
            )

            # ── Thin divider ───────────────────────────────────────────────
            div_y = title_y + 74
            div_grad = QLinearGradient(80, div_y, self.width - 80, div_y)
            div_grad.setColorAt(0.0, QColor(c.BORDER + "00"))
            div_grad.setColorAt(0.2, QColor(c.BORDER))
            div_grad.setColorAt(0.8, QColor(c.BORDER))
            div_grad.setColorAt(1.0, QColor(c.BORDER + "00"))
            painter.setPen(QPen(QBrush(div_grad), 1))
            painter.drawLine(80, div_y, self.width - 80, div_y)

            # ── Status text ─────────────────────────────────────────────────
            status_y = div_y + 20
            status_font = QFont(ty.FONT_UI, ty.SIZE_BODY)
            painter.setFont(status_font)
            painter.setPen(QColor(c.BLUE))
            status_text = self.current_status + "." * self.dot_count
            painter.drawText(
                QRect(0, status_y, self.width, 22),
                Qt.AlignCenter,
                status_text
            )

            # ── Progress bar ────────────────────────────────────────────────
            bar_margin = 64
            bar_x = bar_margin
            bar_y = status_y + 32
            bar_w = self.width - bar_margin * 2
            bar_h = 4

            # Track
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(c.BG_HOVER))
            track_path = QPainterPath()
            track_path.addRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)
            painter.fillPath(track_path, QColor(c.BG_HOVER))

            # Fill
            if self.current_progress > 0:
                fill_w = int(bar_w * self.current_progress / 100)
                fill_grad = QLinearGradient(bar_x, bar_y, bar_x + fill_w, bar_y)
                fill_grad.setColorAt(0.0, QColor(c.GREEN))
                fill_grad.setColorAt(1.0, QColor(c.GREEN_BRIGHT))
                fill_path = QPainterPath()
                fill_path.addRoundedRect(bar_x, bar_y, fill_w, bar_h, 2, 2)
                painter.fillPath(fill_path, fill_grad)

                # Glow on fill end
                if fill_w > 4:
                    glow_x = bar_x + fill_w - 8
                    glow_r = QRadialGradient(glow_x, bar_y + bar_h / 2, 12)
                    glow_r.setColorAt(0.0, QColor(c.GREEN_BRIGHT + "80"))
                    glow_r.setColorAt(1.0, QColor(c.GREEN_BRIGHT + "00"))
                    painter.fillRect(glow_x - 12, bar_y - 8, 24, bar_h + 16, glow_r)

            # Progress % label
            pct_font = QFont(ty.FONT_MONO, ty.SIZE_XS)
            painter.setFont(pct_font)
            painter.setPen(QColor(c.TEXT_MUTED))
            painter.drawText(
                QRect(bar_x + bar_w + 8, bar_y - 2, 40, bar_h + 4),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{self.current_progress}%"
            )

            # ── Copyright ──────────────────────────────────────────────────
            copy_font = QFont(ty.FONT_UI, ty.SIZE_XS)
            painter.setFont(copy_font)
            painter.setPen(QColor(c.TEXT_DISABLED))
            painter.drawText(
                QRect(0, self.height - 24, self.width, 16),
                Qt.AlignCenter,
                "© 2025 Your Company. All rights reserved."
            )

            painter.end()
            self.setPixmap(pixmap)

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._draw_splash] {e}", exc_info=True)

    def _draw_logo_area(self, painter, center_y, c, ty, sp):
        """Draw the logo / chart icon in the upper portion."""
        try:
            cx = self.width // 2
            cy = center_y

            if self.logo_path:
                logo = QPixmap(self.logo_path)
                if not logo.isNull():
                    logo = logo.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    painter.drawPixmap(cx - logo.width() // 2, cy - logo.height() // 2, logo)
                    return

            # Geometric logo: hexagonal bg + chart arrow
            radius = 38

            # Outer glow ring
            glow_r = QRadialGradient(cx, cy, radius + 14)
            glow_r.setColorAt(0.5, QColor(c.BLUE_DARK + "40"))
            glow_r.setColorAt(1.0, QColor(c.BLUE_DARK + "00"))
            painter.fillRect(cx - radius - 14, cy - radius - 14,
                             (radius + 14) * 2, (radius + 14) * 2, glow_r)

            # Hexagon background
            hex_path = QPainterPath()
            for i in range(6):
                angle = math.radians(60 * i - 30)
                x = cx + radius * math.cos(angle)
                y = cy + radius * math.sin(angle)
                if i == 0:
                    hex_path.moveTo(x, y)
                else:
                    hex_path.lineTo(x, y)
            hex_path.closeSubpath()

            hex_grad = QLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
            hex_grad.setColorAt(0.0, QColor(c.BLUE_DARK + "cc"))
            hex_grad.setColorAt(1.0, QColor(c.BG_CARD))
            painter.fillPath(hex_path, hex_grad)

            # Hexagon border
            border_pen = QPen(QColor(c.BLUE + "80"), 1.5)
            painter.setPen(border_pen)
            painter.drawPath(hex_path)

            # Chart line inside hexagon
            painter.setClipPath(hex_path)
            pts = [
                QPointF(cx - 22, cy + 6),
                QPointF(cx - 12, cy - 8),
                QPointF(cx - 2,  cy + 2),
                QPointF(cx + 8,  cy - 12),
                QPointF(cx + 20, cy - 18),
            ]
            chart_pen = QPen(QColor(c.GREEN_BRIGHT), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(chart_pen)
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i], pts[i + 1])

            # Dot at last point
            painter.setPen(Qt.NoPen)
            dot_r = QRadialGradient(pts[-1].x(), pts[-1].y(), 5)
            dot_r.setColorAt(0.0, QColor(c.GREEN_BRIGHT))
            dot_r.setColorAt(1.0, QColor(c.GREEN_BRIGHT + "00"))
            painter.fillRect(int(pts[-1].x()) - 5, int(pts[-1].y()) - 5, 10, 10, dot_r)

            painter.setClipping(False)

        except Exception as e:
            logger.debug(f"[AnimatedSplashScreen._draw_logo_area] {e}")

    def _update_animation(self):
        try:
            if self._closing:
                return
            self.dot_count = (self.dot_count + 1) % 4
            self._tick_count += 1
            self._draw_splash()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._update_animation] {e}", exc_info=True)

    def _on_status_updated(self, status: str):
        try:
            if status is None:
                status = ""
            self.current_status = str(status)
            self._draw_splash()
            self.showMessage(status, Qt.AlignBottom | Qt.AlignCenter, QColor(self._c.BLUE))
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._on_status_updated] {e}", exc_info=True)

    def _on_progress_updated(self, progress: int):
        try:
            progress = int(progress) if progress is not None else 0
            self.current_progress = max(0, min(100, progress))
            self._draw_splash()
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen._on_progress_updated] {e}", exc_info=True)

    def set_status(self, status: str):
        try:
            if status is None:
                status = ""
            self.status_updated.emit(str(status))
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.set_status] {e}", exc_info=True)

    def set_progress(self, progress: int):
        try:
            progress = int(progress) if progress is not None else 0
            progress = max(0, min(100, progress))
            self.progress_updated.emit(progress)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.set_progress] {e}", exc_info=True)

    def finish_with_main_window(self, main_window):
        try:
            if self._closing:
                return
            self.animation_timer.stop()
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(200, self._safe_close)
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.finish_with_main_window] {e}", exc_info=True)
            self._safe_close()

    def _safe_close(self):
        try:
            if not self._closing:
                self.close()
        except Exception as e:
            logger.warning(f"[AnimatedSplashScreen._safe_close] {e}")

    def cleanup(self):
        try:
            if self._closing:
                return
            self._closing = True
            if self.animation_timer and self.animation_timer.isActive():
                self.animation_timer.stop()
                self.animation_timer.timeout.disconnect(self._update_animation)
            self.animation_timer = None
            try:
                self.status_updated.disconnect(self._on_status_updated)
                self.progress_updated.disconnect(self._on_progress_updated)
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.cleanup] {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            self.cleanup()
            super().closeEvent(event)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            event.accept()
        except Exception as e:
            logger.error(f"[AnimatedSplashScreen.closeEvent] {e}", exc_info=True)
            event.accept()


class SplashScreen(QWidget):
    """Standalone splash screen widget (alternative)."""

    def __init__(self, logo_path: Optional[str] = None):
        self._safe_defaults_init()

        try:
            super().__init__()
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.logo_path = logo_path
            if self.logo_path and not os.path.exists(self.logo_path):
                logger.warning(f"[SplashScreen] Logo not found: {self.logo_path}")
                self.logo_path = None

            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            self._center_on_screen()
            self._setup_ui()

            self.dot_count = 0
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._update_animation)
            self.animation_timer.start(400)

            self.apply_theme()
            logger.info("[SplashScreen] Initialized")

        except Exception as e:
            logger.error(f"[SplashScreen.__init__] {e}", exc_info=True)
            super().__init__()

    def _safe_defaults_init(self):
        try:
            self.logo_path      = None
            self.container      = None
            self.logo_label     = None
            self.status_label   = None
            self.progress_bar   = None
            self.progress_label = None
            self.dot_count      = 0
            self.animation_timer = None
            self._closing       = False
            self._is_initialized = False
        except Exception as e:
            logger.error(f"[SplashScreen._safe_defaults_init] {e}", exc_info=True)

    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def apply_theme(self, _: str = None) -> None:
        try:
            if self._closing:
                return
            c, ty, sp = self._c, self._ty, self._sp
            self.setFixedSize(620, 400)

            if self.container:
                self.container.setGeometry(0, 0, 620, 400)
                self.container.setStyleSheet(f"""
                    QFrame {{
                        background: qlineargradient(
                            x1: 0, y1: 0, x2: 1, y2: 1,
                            stop: 0 {c.BG_MAIN}, stop: 0.5 {c.BG_PANEL}, stop: 1 {c.BG_CARD}
                        );
                        border: 1px solid {c.BORDER};
                        border-radius: 12px;
                    }}
                """)

            if self.logo_label:
                self._update_logo()

            if self.status_label:
                self.status_label.setStyleSheet(f"""
                    font-size: {ty.SIZE_BODY}pt;
                    color: {c.BLUE};
                    background: transparent;
                    font-weight: {ty.WEIGHT_MEDIUM};
                """)

            if self.progress_bar:
                self.progress_bar.setFixedHeight(4)
                self.progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: none;
                        background: {c.BG_HOVER};
                        border-radius: 2px;
                        margin: 0 {sp.PAD_2XL}px;
                    }}
                    QProgressBar::chunk {{
                        background: qlineargradient(
                            x1: 0, y1: 0, x2: 1, y2: 0,
                            stop: 0 {c.GREEN}, stop: 1 {c.GREEN_BRIGHT}
                        );
                        border-radius: 2px;
                    }}
                """)

            if self.progress_label:
                self.progress_label.setStyleSheet(f"""
                    font-size: {ty.SIZE_XS}pt;
                    color: {c.TEXT_MUTED};
                    background: transparent;
                    font-family: {ty.FONT_MONO};
                """)

            self._center_on_screen()

        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[SplashScreen.apply_theme] {e}", exc_info=True)

    def _center_on_screen(self):
        try:
            if self._closing:
                return
            screen = QApplication.primaryScreen()
            if screen:
                sr = screen.geometry()
                self.move((sr.width() - self.width()) // 2, (sr.height() - self.height()) // 2)
        except Exception as e:
            logger.error(f"[SplashScreen._center_on_screen] {e}", exc_info=True)

    def _setup_ui(self):
        try:
            c, ty, sp = self._c, self._ty, self._sp

            self.container = QFrame(self)
            self.container.setGeometry(0, 0, 620, 400)

            layout = QVBoxLayout(self.container)
            layout.setContentsMargins(sp.PAD_2XL, sp.PAD_XL, sp.PAD_2XL, sp.PAD_LG)
            layout.setSpacing(sp.GAP_MD)

            # Logo
            self.logo_label = QLabel()
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.logo_label.setFixedHeight(80)
            self._update_logo()
            layout.addWidget(self.logo_label)

            # App name
            app_name = QLabel("Algo Trading Pro")
            app_name.setAlignment(Qt.AlignCenter)
            app_name.setStyleSheet(f"""
                font-size: {ty.SIZE_3XL}pt;
                font-weight: {ty.WEIGHT_BOLD};
                color: {c.TEXT_BRIGHT};
                background: transparent;
                letter-spacing: -0.5px;
            """)
            layout.addWidget(app_name)

            # Version / tagline
            version = QLabel("Professional Algorithmic Trading Platform  ·  v2.0")
            version.setAlignment(Qt.AlignCenter)
            version.setStyleSheet(f"""
                font-size: {ty.SIZE_SM}pt;
                color: {c.TEXT_MUTED};
                background: transparent;
                letter-spacing: 0.3px;
            """)
            layout.addWidget(version)

            # Divider
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet(f"color: {c.BORDER}; background: {c.BORDER}; max-height: 1px; margin: 4px 40px;")
            layout.addWidget(divider)

            layout.addStretch()

            # Status
            self.status_label = QLabel("Initializing...")
            self.status_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.status_label)

            # Progress bar
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(4)
            layout.addWidget(self.progress_bar)

            # Progress %
            self.progress_label = QLabel("0%")
            self.progress_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.progress_label)

            # Copyright
            copyright_lbl = QLabel("© 2025 Your Company. All rights reserved.")
            copyright_lbl.setAlignment(Qt.AlignCenter)
            copyright_lbl.setStyleSheet(f"""
                font-size: {ty.SIZE_XS}pt;
                color: {c.TEXT_DISABLED};
                background: transparent;
            """)
            layout.addWidget(copyright_lbl)

        except Exception as e:
            logger.error(f"[SplashScreen._setup_ui] {e}", exc_info=True)

    def _update_logo(self):
        try:
            if not self.logo_label:
                return
            c, ty = self._c, self._ty
            if self.logo_path:
                try:
                    pix = QPixmap(self.logo_path)
                    if not pix.isNull():
                        pix = pix.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.logo_label.setPixmap(pix)
                        return
                except Exception:
                    pass
            # Text fallback
            self.logo_label.setText("📈")
            self.logo_label.setStyleSheet(f"""
                font-size: 48pt;
                color: {c.BLUE};
                background: transparent;
            """)
        except Exception as e:
            logger.error(f"[SplashScreen._update_logo] {e}", exc_info=True)

    def _update_animation(self):
        try:
            if self._closing or not self.status_label:
                return
            self.dot_count = (self.dot_count + 1) % 4
            dots = "." * self.dot_count
            base = self.status_label.text().rstrip(".")
            if "." in base:
                base = base[:base.rfind(".")]
            self.status_label.setText(base + dots)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
        except Exception as e:
            logger.error(f"[SplashScreen._update_animation] {e}", exc_info=True)

    def set_status(self, status: str):
        try:
            if status is None:
                status = ""
            if self.status_label:
                self.status_label.setText(str(status))
        except Exception as e:
            logger.error(f"[SplashScreen.set_status] {e}", exc_info=True)

    def set_progress(self, progress: int):
        try:
            progress = int(progress) if progress is not None else 0
            progress = max(0, min(100, progress))
            if self.progress_bar:
                self.progress_bar.setValue(progress)
            if self.progress_label:
                self.progress_label.setText(f"{progress}%")
        except Exception as e:
            logger.error(f"[SplashScreen.set_progress] {e}", exc_info=True)

    def cleanup(self):
        try:
            if self._closing:
                return
            self._closing = True
            if self.animation_timer and self.animation_timer.isActive():
                self.animation_timer.stop()
                self.animation_timer.timeout.disconnect(self._update_animation)
            self.animation_timer = None
            try:
                theme_manager.theme_changed.disconnect(self.apply_theme)
                theme_manager.density_changed.disconnect(self.apply_theme)
            except (TypeError, RuntimeError):
                pass
            self.container      = None
            self.logo_label     = None
            self.status_label   = None
            self.progress_bar   = None
            self.progress_label = None
        except Exception as e:
            logger.error(f"[SplashScreen.cleanup] {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            self.cleanup()
            super().closeEvent(event)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                self._closing = True
            event.accept()
        except Exception as e:
            logger.error(f"[SplashScreen.closeEvent] {e}", exc_info=True)
            event.accept()