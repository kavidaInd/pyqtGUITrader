"""
System Monitor Popup - Displays system resource usage and trading app performance metrics
"""
import logging
import psutil
import os
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QGridLayout, QProgressBar, QTabWidget

logger = logging.getLogger(__name__)


class SystemMonitorPopup(QDialog):
    """Popup window for monitoring system resources and trading app performance"""

    def __init__(self, trading_app=None, parent=None):
        super().__init__(parent)
        self.trading_app = trading_app
        self.setWindowTitle("System Monitor")
        self.resize(600, 600)
        self.setMinimumSize(550, 550)

        # Set window flags
        self.setWindowFlags(Qt.Window)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QTabWidget::pane {
                border: 1px solid #30363d;
                background: #0d1117;
            }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                padding: 8px 16px;
                border: 1px solid #30363d;
            }
            QTabBar::tab:selected {
                background: #21262d;
                color: #e6edf3;
                border-bottom: 2px solid #58a6ff;
            }
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
            QLabel#positive { color: #3fb950; }
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
            QProgressBar#disk::chunk { background-color: #8957e5; }
            QPushButton {
                background: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #30363d; }
            QPushButton#dangerBtn {
                background: #da3633;
            }
            QPushButton#dangerBtn:hover {
                background: #f85149;
            }
        """)

        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()

        # Tab 1: System Resources
        system_tab = self._create_system_tab()
        self.tab_widget.addTab(system_tab, "💻 System")

        # Tab 2: Trading App Metrics
        app_tab = self._create_app_tab()
        self.tab_widget.addTab(app_tab, "📊 Trading App")

        # Tab 3: Network Stats
        network_tab = self._create_network_tab()
        self.tab_widget.addTab(network_tab, "🌐 Network")

        layout.addWidget(self.tab_widget)

        # Button row
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("⟳ Refresh Now")
        self.refresh_btn.clicked.connect(self.refresh)

        self.gc_btn = QPushButton("🗑️ Run GC")
        self.gc_btn.setObjectName("dangerBtn")
        self.gc_btn.clicked.connect(self._run_garbage_collection)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.gc_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Store process start time
        self.process_start_time = datetime.now()

    def _create_system_tab(self):
        """Create system resources tab"""
        widget = QGroupBox("System Resources")
        layout = QVBoxLayout(widget)

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

        cpu_info_layout.addWidget(QLabel("Load Average:"), 2, 0)
        self.cpu_load = QLabel("-")
        self.cpu_load.setObjectName("value")
        cpu_info_layout.addWidget(self.cpu_load, 2, 1)

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

        mem_info_layout.addWidget(QLabel("Available:"), 1, 0)
        self.mem_available = QLabel("-")
        self.mem_available.setObjectName("value")
        mem_info_layout.addWidget(self.mem_available, 1, 1)

        mem_info_layout.addWidget(QLabel("Total:"), 2, 0)
        self.mem_total = QLabel("-")
        self.mem_total.setObjectName("value")
        mem_info_layout.addWidget(self.mem_total, 2, 1)

        mem_layout.addLayout(mem_info_layout)
        mem_group.setLayout(mem_layout)
        layout.addWidget(mem_group)

        # Disk Usage Group
        disk_group = QGroupBox("Disk Usage")
        disk_layout = QVBoxLayout()

        self.disk_progress = QProgressBar()
        self.disk_progress.setObjectName("disk")
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

        return widget

    def _create_app_tab(self):
        """Create trading app metrics tab"""
        widget = QGroupBox("Trading Application")
        layout = QVBoxLayout(widget)

        # Process Info
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

        process_layout.addWidget(QLabel("Open FDs:"), 5, 0)
        self.process_fds = QLabel("-")
        self.process_fds.setObjectName("value")
        process_layout.addWidget(self.process_fds, 5, 1)

        process_group.setLayout(process_layout)
        layout.addWidget(process_group)

        # Trading Stats
        trading_group = QGroupBox("Trading Statistics")
        trading_layout = QGridLayout()

        # Row 0
        trading_layout.addWidget(QLabel("Messages/sec:"), 0, 0)
        self.trading_msg_rate = QLabel("0")
        self.trading_msg_rate.setObjectName("value")
        trading_layout.addWidget(self.trading_msg_rate, 0, 1)

        trading_layout.addWidget(QLabel("Queue Size:"), 0, 2)
        self.trading_queue_size = QLabel("0")
        self.trading_queue_size.setObjectName("value")
        trading_layout.addWidget(self.trading_queue_size, 0, 3)

        # Row 1
        trading_layout.addWidget(QLabel("Symbols:"), 1, 0)
        self.trading_symbols = QLabel("0")
        self.trading_symbols.setObjectName("value")
        trading_layout.addWidget(self.trading_symbols, 1, 1)

        trading_layout.addWidget(QLabel("Active Chain:"), 1, 2)
        self.trading_active_chain = QLabel("0")
        self.trading_active_chain.setObjectName("value")
        trading_layout.addWidget(self.trading_active_chain, 1, 3)

        # Row 2
        trading_layout.addWidget(QLabel("Open Orders:"), 2, 0)
        self.trading_open_orders = QLabel("0")
        self.trading_open_orders.setObjectName("value")
        trading_layout.addWidget(self.trading_open_orders, 2, 1)

        trading_layout.addWidget(QLabel("Position:"), 2, 2)
        self.trading_position = QLabel("None")
        self.trading_position.setObjectName("value")
        trading_layout.addWidget(self.trading_position, 2, 3)

        # Row 3
        trading_layout.addWidget(QLabel("Current P&L:"), 3, 0)
        self.trading_pnl = QLabel("₹0.00")
        self.trading_pnl.setObjectName("value")
        trading_layout.addWidget(self.trading_pnl, 3, 1)

        trading_layout.addWidget(QLabel("Signal:"), 3, 2)
        self.trading_signal = QLabel("WAIT")
        self.trading_signal.setObjectName("value")
        trading_layout.addWidget(self.trading_signal, 3, 3)

        trading_group.setLayout(trading_layout)
        layout.addWidget(trading_group)

        # FEATURE 1: Risk Metrics
        risk_group = QGroupBox("Risk Metrics")
        risk_layout = QGridLayout()

        risk_layout.addWidget(QLabel("Daily P&L:"), 0, 0)
        self.risk_daily_pnl = QLabel("₹0.00")
        self.risk_daily_pnl.setObjectName("value")
        risk_layout.addWidget(self.risk_daily_pnl, 0, 1)

        risk_layout.addWidget(QLabel("Trades Today:"), 0, 2)
        self.risk_trades_today = QLabel("0")
        self.risk_trades_today.setObjectName("value")
        risk_layout.addWidget(self.risk_trades_today, 0, 3)

        risk_layout.addWidget(QLabel("Loss Remaining:"), 1, 0)
        self.risk_loss_remaining = QLabel("₹5000")
        self.risk_loss_remaining.setObjectName("value")
        risk_layout.addWidget(self.risk_loss_remaining, 1, 1)

        risk_layout.addWidget(QLabel("Trades Left:"), 1, 2)
        self.risk_trades_left = QLabel("10")
        self.risk_trades_left.setObjectName("value")
        risk_layout.addWidget(self.risk_trades_left, 1, 3)

        risk_group.setLayout(risk_layout)
        layout.addWidget(risk_group)

        layout.addStretch()
        return widget

    def _create_network_tab(self):
        """Create network statistics tab"""
        widget = QGroupBox("Network Statistics")
        layout = QVBoxLayout(widget)

        # WebSocket Stats
        ws_group = QGroupBox("WebSocket Connection")
        ws_layout = QGridLayout()

        ws_layout.addWidget(QLabel("Status:"), 0, 0)
        self.ws_status = QLabel("Disconnected")
        self.ws_status.setObjectName("value")
        ws_layout.addWidget(self.ws_status, 0, 1)

        ws_layout.addWidget(QLabel("Messages:"), 1, 0)
        self.ws_messages = QLabel("0")
        self.ws_messages.setObjectName("value")
        ws_layout.addWidget(self.ws_messages, 1, 1)

        ws_layout.addWidget(QLabel("Errors:"), 1, 2)
        self.ws_errors = QLabel("0")
        self.ws_errors.setObjectName("value")
        ws_layout.addWidget(self.ws_errors, 1, 3)

        ws_layout.addWidget(QLabel("Reconnects:"), 2, 0)
        self.ws_reconnects = QLabel("0")
        self.ws_reconnects.setObjectName("value")
        ws_layout.addWidget(self.ws_reconnects, 2, 1)

        ws_layout.addWidget(QLabel("Last Message:"), 2, 2)
        self.ws_last_msg = QLabel("-")
        self.ws_last_msg.setObjectName("value")
        ws_layout.addWidget(self.ws_last_msg, 2, 3)

        ws_group.setLayout(ws_layout)
        layout.addWidget(ws_group)

        # Network I/O
        io_group = QGroupBox("Network I/O")
        io_layout = QGridLayout()

        io_layout.addWidget(QLabel("Bytes Sent:"), 0, 0)
        self.net_bytes_sent = QLabel("0 B")
        self.net_bytes_sent.setObjectName("value")
        io_layout.addWidget(self.net_bytes_sent, 0, 1)

        io_layout.addWidget(QLabel("Bytes Received:"), 0, 2)
        self.net_bytes_recv = QLabel("0 B")
        self.net_bytes_recv.setObjectName("value")
        io_layout.addWidget(self.net_bytes_recv, 0, 3)

        io_layout.addWidget(QLabel("Packets Sent:"), 1, 0)
        self.net_packets_sent = QLabel("0")
        self.net_packets_sent.setObjectName("value")
        io_layout.addWidget(self.net_packets_sent, 1, 1)

        io_layout.addWidget(QLabel("Packets Received:"), 1, 2)
        self.net_packets_recv = QLabel("0")
        self.net_packets_recv.setObjectName("value")
        io_layout.addWidget(self.net_packets_recv, 1, 3)

        io_group.setLayout(io_layout)
        layout.addWidget(io_group)

        # Connection Info
        conn_group = QGroupBox("Active Connections")
        conn_layout = QVBoxLayout()

        self.conn_list = QLabel("No active connections")
        self.conn_list.setWordWrap(True)
        self.conn_list.setStyleSheet("color: #8b949e; font-size: 9pt;")
        conn_layout.addWidget(self.conn_list)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        layout.addStretch()
        return widget

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

    def _run_garbage_collection(self):
        """Force garbage collection"""
        try:
            import gc
            before = gc.get_count()
            collected = gc.collect()
            after = gc.get_count()
            logger.info(f"GC: collected {collected} objects, counts: {before} -> {after}")
            self.refresh_btn.setText(f"✅ GC: {collected} collected")
            QTimer.singleShot(2000, lambda: self.refresh_btn.setText("⟳ Refresh Now"))
        except Exception as e:
            logger.error(f"[SystemMonitorPopup._run_garbage_collection] Failed: {e}")

    def refresh(self):
        """Refresh all metrics"""
        try:
            self._refresh_system_metrics()
            self._refresh_app_metrics()
            self._refresh_network_metrics()

            # Update styles
            self.cpu_progress.style().unpolish(self.cpu_progress)
            self.cpu_progress.style().polish(self.cpu_progress)

        except Exception as e:
            logger.error(f"[SystemMonitorPopup.refresh] Failed: {e}")

    def _refresh_system_metrics(self):
        """Refresh system resource metrics"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_progress.setValue(int(cpu_percent))

            # CPU frequency
            freq = psutil.cpu_freq()
            if freq:
                self.cpu_freq.setText(f"{freq.current:.0f} MHz")

            # Load average
            try:
                load_avg = psutil.getloadavg()
                self.cpu_load.setText(f"{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}")
            except:
                self.cpu_load.setText("N/A")

            # Memory
            mem = psutil.virtual_memory()
            self.mem_progress.setValue(int(mem.percent))
            self.mem_used.setText(self._format_bytes(mem.used))
            self.mem_available.setText(self._format_bytes(mem.available))
            self.mem_total.setText(self._format_bytes(mem.total))

            # Disk (current directory)
            disk = psutil.disk_usage('.')
            self.disk_progress.setValue(int(disk.used / disk.total * 100))
            self.disk_used.setText(self._format_bytes(disk.used))
            self.disk_free.setText(self._format_bytes(disk.free))
            self.disk_total.setText(self._format_bytes(disk.total))

            # Color code CPU based on usage
            if cpu_percent > 90:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: #f85149; }")
            elif cpu_percent > 70:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: #d29922; }")
            else:
                self.cpu_progress.setStyleSheet("QProgressBar::chunk { background-color: #58a6ff; }")

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._refresh_system_metrics] Failed: {e}")

    def _refresh_app_metrics(self):
        """Refresh trading app metrics"""
        try:
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

            # Open file descriptors
            try:
                self.process_fds.setText(str(len(process.open_files())))
            except:
                self.process_fds.setText("N/A")

            # Trading stats from app
            if self.trading_app:
                # Queue size
                if hasattr(self.trading_app, '_tick_queue'):
                    self.trading_queue_size.setText(str(self.trading_app._tick_queue.qsize()))

                # Symbols
                if hasattr(self.trading_app.state, 'all_symbols'):
                    symbols = self.trading_app.state.all_symbols or []
                    self.trading_symbols.setText(str(len(symbols)))

                # Active chain
                if hasattr(self.trading_app.state, 'option_chain'):
                    chain = self.trading_app.state.option_chain or {}
                    active = sum(1 for data in chain.values() if data and data.get('ltp'))
                    self.trading_active_chain.setText(str(active))

                # Open orders
                if hasattr(self.trading_app.state, 'orders'):
                    orders = self.trading_app.state.orders or []
                    self.trading_open_orders.setText(str(len(orders)))

                # Position
                if hasattr(self.trading_app.state, 'current_position'):
                    pos = self.trading_app.state.current_position
                    self.trading_position.setText(pos if pos else "None")

                # P&L
                if hasattr(self.trading_app.state, 'current_pnl'):
                    pnl = self.trading_app.state.current_pnl or 0
                    self.trading_pnl.setText(f"₹{pnl:,.2f}")
                    # Color based on P&L
                    if pnl > 0:
                        self.trading_pnl.setProperty("cssClass", "positive")
                    elif pnl < 0:
                        self.trading_pnl.setProperty("cssClass", "critical")
                    else:
                        self.trading_pnl.setProperty("cssClass", "value")

                # Signal
                if hasattr(self.trading_app.state, 'option_signal'):
                    signal = self.trading_app.state.option_signal or "WAIT"
                    self.trading_signal.setText(signal)

                # FEATURE 1: Risk metrics
                if hasattr(self.trading_app, 'risk_manager'):
                    risk = self.trading_app.risk_manager
                    config = self.trading_app.config if hasattr(self.trading_app, 'config') else None
                    summary = risk.get_risk_summary(config)

                    pnl = summary.get('pnl_today', 0)
                    self.risk_daily_pnl.setText(f"₹{pnl:,.2f}")
                    if pnl > 0:
                        self.risk_daily_pnl.setProperty("cssClass", "positive")
                    elif pnl < 0:
                        self.risk_daily_pnl.setProperty("cssClass", "critical")

                    self.risk_trades_today.setText(str(summary.get('trades_today', 0)))
                    self.risk_loss_remaining.setText(f"₹{summary.get('max_loss_remaining', 5000):,.2f}")
                    self.risk_trades_left.setText(str(summary.get('max_trades_remaining', 10)))

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._refresh_app_metrics] Failed: {e}")

    def _refresh_network_metrics(self):
        """Refresh network metrics"""
        try:
            # WebSocket stats from app
            if self.trading_app and hasattr(self.trading_app, 'ws') and self.trading_app.ws:
                ws = self.trading_app.ws

                # Status
                if hasattr(ws, 'is_connected') and ws.is_connected():
                    self.ws_status.setText("Connected")
                    self.ws_status.setProperty("cssClass", "positive")
                else:
                    self.ws_status.setText("Disconnected")
                    self.ws_status.setProperty("cssClass", "critical")

                # Statistics
                if hasattr(ws, 'get_statistics'):
                    stats = ws.get_statistics()
                    self.ws_messages.setText(str(stats.get('message_count', 0)))
                    self.ws_errors.setText(str(stats.get('error_count', 0)))
                    self.ws_reconnects.setText(str(stats.get('reconnect_count', 0)))

                # Last message time
                if hasattr(ws, '_last_message_time') and ws._last_message_time:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ws._last_message_time)
                    self.ws_last_msg.setText(dt.strftime("%H:%M:%S"))
            else:
                self.ws_status.setText("No WebSocket")
                self.ws_status.setProperty("cssClass", "value")

            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io:
                self.net_bytes_sent.setText(self._format_bytes(net_io.bytes_sent))
                self.net_bytes_recv.setText(self._format_bytes(net_io.bytes_recv))
                self.net_packets_sent.setText(str(net_io.packets_sent))
                self.net_packets_recv.setText(str(net_io.packets_recv))

            # Active connections
            try:
                connections = psutil.net_connections()
                # Filter to relevant connections (Fyers API)
                fyers_conns = [c for c in connections if c.raddr and 'fyers' in str(c.raddr).lower()]
                if fyers_conns:
                    conn_text = f"Fyers: {len(fyers_conns)} connection(s)"
                else:
                    conn_text = "No Fyers connections"
                self.conn_list.setText(conn_text)
            except (psutil.AccessDenied, psutil.Error):
                self.conn_list.setText("Connection info unavailable (need admin rights)")

            # Update styles
            self.ws_status.style().unpolish(self.ws_status)
            self.ws_status.style().polish(self.ws_status)
            self.trading_pnl.style().unpolish(self.trading_pnl)
            self.trading_pnl.style().polish(self.trading_pnl)
            self.risk_daily_pnl.style().unpolish(self.risk_daily_pnl)
            self.risk_daily_pnl.style().polish(self.risk_daily_pnl)

        except Exception as e:
            logger.error(f"[SystemMonitorPopup._refresh_network_metrics] Failed: {e}")

    def closeEvent(self, event):
        """Handle close event"""
        try:
            self.timer.stop()
            event.accept()
        except Exception as e:
            logger.error(f"[SystemMonitorPopup.closeEvent] Failed: {e}")
            event.accept()