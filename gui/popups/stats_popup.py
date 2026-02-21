from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton


class StatsPopup(QDialog):
    """Popup window for displaying statistics"""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Trading Statistics")
        self.resize(900, 700)
        self.setMinimumSize(700, 500)

        # Set window flags to make it a proper popup
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
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
        from gui.stats_tab import StatsTab
        self.stats_tab = StatsTab(self.state)
        layout.addWidget(self.stats_tab)

        # Refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(2000)  # Refresh every 2 seconds

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def refresh(self):
        """Refresh statistics"""
        if hasattr(self.stats_tab, 'refresh'):
            self.stats_tab.refresh()

    def closeEvent(self, event):
        """Stop timer when closing"""
        self.refresh_timer.stop()
        event.accept()
