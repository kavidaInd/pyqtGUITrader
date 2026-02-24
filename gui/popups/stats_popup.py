import logging
import logging.handlers
import traceback
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class StatsPopup(QDialog):
    """Popup window for displaying statistics"""

    def __init__(self, state, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.state = state
            self.setWindowTitle("Trading Statistics")
            self.resize(900, 700)
            self.setMinimumSize(700, 500)

            # Set window flags to make it a proper popup
            self.setWindowFlags(Qt.Window)

            # EXACT stylesheet preservation
            self.setStyleSheet("""
                QDialog { background: #0d1117; color: #e6edf3; }
                QTabWidget::pane { border: 1px solid #30363d; }
                QTabBar::tab { background: #161b22; color: #8b949e;
                              padding: 8px 16px; border: 1px solid #30363d; }
                QTabBar::tab:selected { background: #21262d; color: #e6edf3;
                                        border-bottom: 2px solid #58a6ff; }
                QLabel { color: #e6edf3; font-size: 10pt; }
                QLabel[cssClass="value"] { color: #58a6ff; font-weight: bold; }
                QLabel[cssClass="positive"] { color: #3fb950; }
                QLabel[cssClass="negative"] { color: #f85149; }
                QGroupBox {
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    margin-top: 10px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QPushButton {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background: #30363d; }
            """)

            layout = QVBoxLayout(self)

            # Import StatsTab and add it
            try:
                from gui.stats_tab import StatsTab
                self.stats_tab = StatsTab(self.state)
                layout.addWidget(self.stats_tab)
            except ImportError as e:
                logger.error(f"Failed to import StatsTab: {e}", exc_info=True)
                # Add error message to layout
                error_label = QLabel(f"Failed to load statistics tab: {e}")
                error_label.setStyleSheet("color: #f85149; padding: 20px;")
                layout.addWidget(error_label)
                self.stats_tab = None
            except Exception as e:
                logger.error(f"Failed to create StatsTab: {e}", exc_info=True)
                error_label = QLabel(f"Failed to create statistics tab: {e}")
                error_label.setStyleSheet("color: #f85149; padding: 20px;")
                layout.addWidget(error_label)
                self.stats_tab = None

            # Refresh timer
            self.refresh_timer = QTimer(self)
            self.refresh_timer.timeout.connect(self.refresh)
            self.refresh_timer.start(2000)  # Refresh every 2 seconds

            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

            logger.info("StatsPopup initialized")

        except Exception as e:
            logger.critical(f"[StatsPopup.__init__] Failed: {e}", exc_info=True)
            # Still try to create basic dialog
            super().__init__(parent)
            self.setWindowTitle("Statistics - ERROR")
            self.setMinimumSize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QLabel(f"Failed to initialize statistics popup:\n{e}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.state = None
        self.stats_tab = None
        self.refresh_timer = None

    def refresh(self):
        """Refresh statistics"""
        try:
            # Rule 6: Check if we should refresh
            if self.stats_tab is None:
                logger.debug("refresh called with None stats_tab")
                return

            if hasattr(self.stats_tab, 'refresh') and callable(self.stats_tab.refresh):
                try:
                    self.stats_tab.refresh()
                    logger.debug("Statistics refreshed")
                except Exception as e:
                    logger.error(f"Failed to refresh stats tab: {e}", exc_info=True)
            else:
                logger.warning("stats_tab has no refresh method")

        except Exception as e:
            logger.error(f"[StatsPopup.refresh] Failed: {e}", exc_info=True)

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[StatsPopup] Starting cleanup")

            # Stop timer - FIXED: Use explicit None check
            if self.refresh_timer is not None:
                try:
                    if self.refresh_timer.isActive():
                        self.refresh_timer.stop()
                    self.refresh_timer = None
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear stats tab - FIXED: Use explicit None check
            if self.stats_tab is not None:
                try:
                    if hasattr(self.stats_tab, 'cleanup'):
                        self.stats_tab.cleanup()
                except Exception as e:
                    logger.warning(f"Error cleaning up stats tab: {e}")
                self.stats_tab = None

            # Clear state reference
            self.state = None

            logger.info("[StatsPopup] Cleanup completed")

        except Exception as e:
            logger.error(f"[StatsPopup.cleanup] Error: {e}", exc_info=True)

    def closeEvent(self, event):
        """Stop timer when closing and cleanup"""
        try:
            self.cleanup()
            event.accept()
        except Exception as e:
            logger.error(f"[StatsPopup.closeEvent] Failed: {e}", exc_info=True)
            event.accept()

    def accept(self):
        """Handle accept with cleanup"""
        try:
            self.cleanup()
            super().accept()
        except Exception as e:
            logger.error(f"[StatsPopup.accept] Failed: {e}", exc_info=True)
            super().accept()