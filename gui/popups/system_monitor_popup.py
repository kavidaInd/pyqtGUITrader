"""
System Monitor Popup - Displays system resource usage and performance metrics
"""
import logging
import psutil
import os
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout, QProgressBar

logger = logging.getLogger(__name__)


class SystemMonitorPopup(QDialog):
    """Popup window for monitoring system resources"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Monitor")
        self.resize(500, 500)
        self.setMinimumSize(450, 450)

        # Set window flags
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QGroupBox {
                border: 1px solid #30363d;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #e6edf3;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel { color: #e6edf3; }
            QLabel#value { color: #58a6ff; font-weight: bold; }
            QLabel#warning { color: #d29922; }
            QLabel#critical { color: #f85149; }
            QProgressBar {
                border: 1px solid #30363d;
                border-radius: 3px;
                text-align: center;
                color: #e6edf3;
            }
            QProgressBar::chunk {
                background-color: #58a6ff;
                border-radius: 3px;
            }
            QProgressBar#memory::chunk { background-color: #3fb950; }
            QProgressBar#cpu::chunk { background-color: #d29922; }
            QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #30363d; }
        """)

        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # CPU Usage Group
        cpu_group = QGroupBox("CPU Usage")
        cpu_layout = QVBoxLayout()

        self.cpu_progress = QProgressBar()
        self.cpu_progress.setObjectName("cpu")
        self.cpu_progress.setRange(0, 100)
        cpu_layout.addWidget(self.cpu_progress)

        cpu_info_layout = QGridLayout()
        cpu_info_layout.addWidget(QLabel("Cores:"), 0, 0)
        self.cpu_cores = QLabel(str(psutil.cpu_count()))
        self.cpu_cores.setObjectName("value")
        cpu_info_layout.addWidget(self.cpu_cores, 0, 1)

        cpu_info_layout.addWidget(QLabel("Frequency:"), 1, 0)
        self.cpu_freq = QLabel("-")
        self.cpu_freq.setObjectName("value")
        cpu_info_layout.addWidget(self.cpu_freq, 1, 1)

        cpu_layout.addLayout(cpu_info_layout)
        cpu_group.setLayout(cpu_layout)
        layout.addWidget(cpu_group)

        # Memory Usage Group
        mem_group = QGroupBox("Memory Usage")
        mem_layout = QVBoxLayout()

        self.mem_progress = QProgressBar()
        self.mem_progress.setObjectName("memory")
        self.mem_progress.setRange(0, 100)
        mem_layout.addWidget(self.mem_progress)

        mem_info_layout = QGridLayout()
        mem_info_layout.addWidget(QLabel("Used:"), 0, 0)
        self.mem_used = QLabel("-")
        self.mem_used.setObjectName("value")
        mem_info_layout.addWidget(self.mem_used, 0, 1)

        mem_info_layout.addWidget(QLabel("Total:"), 1, 0)
        self.mem_total = QLabel("-")
        self.mem_total.setObjectName("value")
        mem_info_layout.addWidget(self.mem_total, 1, 1)

        mem_layout.addLayout(mem_info_layout)
        mem_group.setLayout(mem_layout)
        layout.addWidget(mem_group)

        # Disk Usage Group
        disk_group = QGroupBox("Disk Usage")
        disk_layout = QVBoxLayout()

        self.disk_progress = QProgressBar()
        self.disk_progress.setRange(0, 100)
        disk_layout.addWidget(self.disk_progress)

        disk_info_layout = QGridLayout()
        disk_info_layout.addWidget(QLabel("Used:"), 0, 0)
        self.disk_used = QLabel("-")
        self.disk_used.setObjectName("value")
        disk_info_layout.addWidget(self.disk_used, 0, 1)

        disk_info_layout.addWidget(QLabel("Free:"), 1, 0)
        self.disk_free = QLabel("-")
        self.disk_free.setObjectName("value")
        disk_info_layout.addWidget(self.disk_free, 1, 1)

        disk_info_layout.addWidget(QLabel("Total:"), 2, 0)
        self.disk_total = QLabel("-")
        self.disk_total.setObjectName("value")
        disk_info_layout.addWidget(self.disk_total, 2, 1)

        disk_layout.addLayout(disk_info_layout)
        disk_group.setLayout(disk_layout)
        layout.addWidget(disk_group)

        # Process Info Group
        process_group = QGroupBox("Process Info")
        process_layout = QGridLayout()

        process_layout.addWidget(QLabel("PID:"), 0, 0)
        self.process_pid = QLabel(str(os.getpid()))
        self.process_pid.setObjectName("value")
        process_layout.addWidget(self.process_pid, 0, 1)

        process_layout.addWidget(QLabel("Threads:"), 1, 0)
        self.process_threads = QLabel("-")
        self.process_threads.setObjectName("value")
        process_layout.addWidget(self.process_threads, 1, 1)

        process_layout.addWidget(QLabel("Memory (RSS):"), 2, 0)
        self.process_memory = QLabel("-")
        self.process_memory.setObjectName("value")
        process_layout.addWidget(self.process_memory, 2, 1)

        process_layout.addWidget(QLabel("CPU %:"), 3, 0)
        self.process_cpu = QLabel("-")
        self.process_cpu.setObjectName("value")
        process_layout.addWidget(self.process_cpu, 3, 1)

        process_layout.addWidget(QLabel("Uptime:"), 4, 0)
        self.process_uptime = QLabel("-")
        self.process_uptime.setObjectName("value")
        process_layout.addWidget(self.process_uptime, 4, 1)

        process_group.setLayout(process_layout)
        layout.addWidget(process_group)

        # Button row
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self.refresh)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_layout.addStretch()
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Store process start time
        self.process_start_time = datetime.now()

    def _init_timer(self):
        """Initialize refresh timer"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)  # Refresh every 2 seconds

    def _format_bytes(self, bytes_val):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"

    def refresh(self):
        """Refresh system metrics"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_progress.setValue(int(cpu_percent))

            # CPU frequency
            freq = psutil.cpu_freq()
            if freq:
                self.cpu_freq.setText(f"{freq.current:.0f} MHz")

            # Memory
            mem = psutil.virtual_memory()
            self.mem_progress.setValue(int(mem.percent))
            self.mem_used.setText(self._format_bytes(mem.used))
            self.mem_total.setText(self._format_bytes(mem.total))

            # Disk (current directory)
            disk = psutil.disk_usage('.')
            self.disk_progress.setValue(int(disk.used / disk.total * 100))
            self.disk_used.setText(self._format_bytes(disk.used))
            self.disk_free.setText(self._format_bytes(disk.free))
            self.disk_total.setText(self._format_bytes(disk.total))

            # Process info
            process = psutil.Process()

            # Threads
            self.process_threads.setText(str(process.num_threads()))

            # Memory
            mem_info = process.memory_info()
            self.process_memory.setText(self._format_bytes(mem_info.rss))

            # CPU
            self.process_cpu.setText(f"{process.cpu_percent(interval=0.1):.1f}%")

            # Uptime
            create_time = datetime.fromtimestamp(process.create_time())
            uptime = datetime.now() - create_time
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds % 3600) // 60
            seconds = uptime.seconds % 60
            self.process_uptime.setText(f"{hours}h {minutes}m {seconds}s")

            # Color code CPU based on usage
            if cpu_percent > 90:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: #f85149; }")
            elif cpu_percent > 70:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: #d29922; }")
            else:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: #58a6ff; }")

        except Exception as e:
            logger.error(f"[SystemMonitorPopup.refresh] Failed: {e}")

    def closeEvent(self, event):
        """Handle close event"""
        try:
            self.timer.stop()
            event.accept()
        except Exception as e:
            logger.error(f"[SystemMonitorPopup.closeEvent] Failed: {e}")
            event.accept()