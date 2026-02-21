from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QPushButton


class LogPopup(QDialog):
    """Popup window for displaying logs"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)

        # Set window flags to make it a proper popup
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QPlainTextEdit { 
                background: #0d1117; 
                color: #58a6ff; 
                border: 1px solid #30363d;
                font-family: Consolas;
                font-size: 10pt;
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Log widget
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumBlockCount(5000)
        layout.addWidget(self.log_widget)

        # Button row
        button_box = QDialogButtonBox()
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_box.addButton(clear_btn, QDialogButtonBox.ActionRole)
        button_box.addButton(close_btn, QDialogButtonBox.AcceptRole)
        layout.addWidget(button_box)

    def append_log(self, message: str):
        """Append a log message to the widget"""
        print(f"🟣 Popup.append_log: {message[:50]}...")  # Debug

        # Get current text count before adding
        before_count = self.log_widget.blockCount()
        print(f"Before: {before_count} blocks")

        self.log_widget.appendPlainText(message)

        # Check if it was added
        after_count = self.log_widget.blockCount()
        print(f"After: {after_count} blocks, Added: {after_count - before_count}")

        # Force update
        self.log_widget.repaint()

        # Auto-scroll to bottom
        sb = self.log_widget.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_logs(self):
        """Clear all logs"""
        self.log_widget.clear()
