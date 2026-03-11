"""
Backtest GUI window for running and viewing backtest results.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QProgressBar, QTextEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QSplitter,
    QMessageBox, QCheckBox, QWidget, QFileDialog
)

from backtest.backtest_engine import BacktestEngine, BacktestResult
from config import Config
from strategy.strategy_manager import StrategyManager

from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


class BacktestWorker(QThread):
    """
    Worker thread for running backtests without freezing GUI.
    """
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, config, broker, strategy_manager, params):
        super().__init__()
        self.config = config
        self.strategy_manager = strategy_manager
        self.params = params
        self._is_cancelled = False

    def run(self):
        try:
            engine = BacktestEngine(self.config, self.strategy_manager)
            engine.set_callbacks(
                progress_callback=self.progress_updated.emit,
                status_callback=self.status_updated.emit
            )

            result = engine.run_backtest(**self.params)

            if not self._is_cancelled:
                self.result_ready.emit(result)

        except Exception as e:
            if not self._is_cancelled:
                self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()

    def cancel(self):
        self._is_cancelled = True


class BacktestGUI(QDialog):
    """
    Backtest configuration and results window.
    """

    def __init__(self, config: Config, strategy_manager: StrategyManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.strategy_manager = strategy_manager
        self.current_result: Optional[BacktestResult] = None
        self.worker: Optional[BacktestWorker] = None

        self.setWindowTitle("Backtest Engine")
        self.setMinimumSize(1200, 800)
        self.setWindowFlags(Qt.Window)

        self._setup_ui()
        self._connect_signals()
        self.apply_theme()

        theme_manager.theme_changed.connect(self.apply_theme)
        theme_manager.density_changed.connect(self.apply_theme)

    # ── theme shortcuts ──────────────────────────────────────────────────────
    @property
    def _c(self):  return theme_manager.palette
    @property
    def _ty(self): return theme_manager.typography
    @property
    def _sp(self): return theme_manager.spacing

    def apply_theme(self, _=None):
        """Apply theme to the entire backtest window."""
        try:
            c  = self._c
            ty = self._ty
            sp = self._sp
            self.setStyleSheet(f"""
                QDialog, QWidget {{
                    background: {c.BG_MAIN};
                    color: {c.TEXT_MAIN};
                    font-size: {ty.SIZE_SM}pt;
                }}
                QGroupBox {{
                    background: {c.BG_PANEL};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    margin-top: 8px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    color: {c.TEXT_DIM};
                    padding-top: 4px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: {sp.PAD_MD}px;
                    padding: 0 4px;
                    color: {c.TEXT_DIM};
                }}
                QLabel {{
                    color: {c.TEXT_MAIN};
                    background: transparent;
                }}
                QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
                    background: {c.BG_CARD};
                    color: {c.TEXT_MAIN};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {ty.SIZE_SM}pt;
                    min-height: {sp.BTN_HEIGHT_SM}px;
                }}
                QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
                QDateEdit:focus, QComboBox:focus {{
                    border-color: {c.BLUE};
                }}
                QComboBox::drop-down {{ border: none; }}
                QComboBox::down-arrow {{ width: 12px; height: 12px; }}
                QCheckBox {{
                    color: {c.TEXT_MAIN};
                    spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: 14px; height: 14px;
                    border: 1px solid {c.BORDER};
                    border-radius: 3px;
                    background: {c.BG_CARD};
                }}
                QCheckBox::indicator:checked {{
                    background: {c.BLUE};
                    border-color: {c.BLUE};
                }}
                QPushButton {{
                    background: {c.BG_CARD};
                    color: {c.TEXT_MAIN};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    min-height: {sp.BTN_HEIGHT_SM}px;
                }}
                QPushButton:hover   {{ background: {c.BG_HOVER}; border-color: {c.BORDER_STRONG}; }}
                QPushButton:pressed {{ background: {c.BG_MAIN}; }}
                QPushButton:disabled {{ color: {c.TEXT_DISABLED}; border-color: {c.BORDER_DIM}; }}
                QTableWidget {{
                    background: {c.BG_PANEL};
                    color: {c.TEXT_MAIN};
                    gridline-color: {c.BORDER_DIM};
                    border: 1px solid {c.BORDER};
                    font-size: {ty.SIZE_SM}pt;
                    alternate-background-color: {c.BG_ROW_B};
                    selection-background-color: {c.BG_SELECTED};
                }}
                QTableWidget::item {{ padding: 3px; }}
                QHeaderView::section {{
                    background: {c.BG_CARD};
                    color: {c.TEXT_DIM};
                    border: none;
                    border-right: 1px solid {c.BORDER_DIM};
                    border-bottom: 1px solid {c.BORDER};
                    padding: {sp.PAD_XS}px {sp.PAD_SM}px;
                    font-size: {ty.SIZE_XS}pt;
                    font-weight: {ty.WEIGHT_BOLD};
                    letter-spacing: 0.5px;
                }}
                QTextEdit {{
                    background: {c.BG_MAIN};
                    color: {c.GREEN};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    font-family: Consolas, monospace;
                    font-size: {ty.SIZE_SM}pt;
                }}
                QProgressBar {{
                    background: {c.BG_CARD};
                    border: 1px solid {c.BORDER};
                    border-radius: {sp.RADIUS_SM}px;
                    text-align: center;
                    color: {c.TEXT_MAIN};
                    min-height: {sp.PROGRESS_MD}px;
                    max-height: {sp.PROGRESS_MD}px;
                }}
                QProgressBar::chunk {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 {c.BLUE_DARK}, stop:1 {c.BLUE_BRIGHT});
                    border-radius: {sp.RADIUS_SM}px;
                }}
                QSplitter::handle {{ background: {c.BORDER_DIM}; }}
                QSplitter::handle:horizontal {{ width: 1px; }}
                QTabWidget::pane {{
                    border: 1px solid {c.BORDER};
                    border-top: none;
                    border-radius: 0 0 {sp.RADIUS_MD}px {sp.RADIUS_MD}px;
                    background: {c.BG_MAIN};
                }}
                QTabBar::tab {{
                    background: {c.BG_CARD};
                    color: {c.TEXT_DIM};
                    padding: {sp.PAD_XS}px {sp.PAD_LG}px;
                    border: 1px solid {c.BORDER};
                    border-bottom: none;
                    border-radius: {sp.RADIUS_MD}px {sp.RADIUS_MD}px 0 0;
                    font-size: {ty.SIZE_SM}pt;
                    font-weight: 600;
                    margin-right: 2px;
                }}
                QTabBar::tab:selected {{
                    background: {c.BG_MAIN};
                    color: {c.TEXT_BRIGHT};
                    border-bottom: 2px solid {c.BLUE};
                    font-weight: {ty.WEIGHT_BOLD};
                }}
                QTabBar::tab:hover:!selected {{
                    background: {c.BG_HOVER};
                    color: {c.TEXT_MAIN};
                }}
                QScrollBar:vertical {{
                    background: {c.BG_PANEL}; width: 8px; border-radius: 4px; margin: 0;
                }}
                QScrollBar::handle:vertical {{
                    background: {c.BORDER}; min-height: 20px; border-radius: 4px;
                }}
                QScrollBar::handle:vertical:hover {{ background: {c.BORDER_STRONG}; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """)
            # Style Run button as primary green
            if hasattr(self, 'run_btn') and self.run_btn:
                self.run_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                    stop:0 {c.GREEN}, stop:1 {c.GREEN_DARK});
                        color: {c.TEXT_INVERSE};
                        border: none;
                        border-radius: {sp.RADIUS_SM}px;
                        padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                        font-weight: {ty.WEIGHT_BOLD};
                        min-height: {sp.BTN_HEIGHT_SM}px;
                    }}
                    QPushButton:hover {{ background: {c.GREEN_BRIGHT}; }}
                    QPushButton:disabled {{ background: {c.BG_HOVER}; color: {c.TEXT_DISABLED}; }}
                """)
            if hasattr(self, 'cancel_btn') and self.cancel_btn:
                self.cancel_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                    stop:0 {c.RED}, stop:1 {c.RED_DARK});
                        color: {c.TEXT_INVERSE};
                        border: none;
                        border-radius: {sp.RADIUS_SM}px;
                        padding: {sp.PAD_XS}px {sp.PAD_MD}px;
                        font-weight: {ty.WEIGHT_BOLD};
                        min-height: {sp.BTN_HEIGHT_SM}px;
                    }}
                    QPushButton:hover {{ background: {c.RED_BRIGHT}; }}
                """)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[BacktestGUI.apply_theme] {{e}}")

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Splitter for config and results
        splitter = QSplitter(Qt.Horizontal)

        # Left panel - Configuration
        left_widget = self._create_config_panel()
        splitter.addWidget(left_widget)

        # Right panel - Results (tabbed)
        right_widget = self._create_results_panel()
        splitter.addWidget(right_widget)

        splitter.setSizes([400, 800])
        main_layout.addWidget(splitter)

        # Bottom status bar
        status_layout = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)

        main_layout.addLayout(status_layout)

    def _create_config_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Symbol selection
        symbol_group = QGroupBox("Instrument")
        symbol_layout = QFormLayout()

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(["NIFTY50-INDEX", "BANKNIFTY-INDEX"])
        symbol_layout.addRow("Symbol:", self.symbol_combo)

        symbol_group.setLayout(symbol_layout)
        layout.addWidget(symbol_group)

        # Date range
        date_group = QGroupBox("Date Range")
        date_layout = QFormLayout()

        # Default to last 30 days
        today = datetime.now().date()
        self.start_date = QDateEdit()
        self.start_date.setDate(today - timedelta(days=30))
        self.start_date.setCalendarPopup(True)
        date_layout.addRow("Start Date:", self.start_date)

        self.end_date = QDateEdit()
        self.end_date.setDate(today - timedelta(days=1))
        self.end_date.setCalendarPopup(True)
        date_layout.addRow("End Date:", self.end_date)

        date_group.setLayout(date_layout)
        layout.addWidget(date_group)

        # Timeframe
        tf_group = QGroupBox("Timeframe")
        tf_layout = QFormLayout()

        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["1m", "2m", "5m", "10m", "15m", "30m", "1h", "1d"])
        self.interval_combo.setCurrentText("2m")
        tf_layout.addRow("Interval:", self.interval_combo)

        tf_group.setLayout(tf_layout)
        layout.addWidget(tf_group)

        # Capital settings
        capital_group = QGroupBox("Capital & Position Sizing")
        capital_layout = QFormLayout()

        self.initial_capital = QDoubleSpinBox()
        self.initial_capital.setRange(1000, 10000000)
        self.initial_capital.setValue(100000)
        self.initial_capital.setSingleStep(10000)
        self.initial_capital.setPrefix("₹ ")
        capital_layout.addRow("Initial Capital:", self.initial_capital)

        self.lot_size = QSpinBox()
        self.lot_size.setRange(1, 1000)
        self.lot_size.setValue(75)
        capital_layout.addRow("Lot Size:", self.lot_size)

        capital_group.setLayout(capital_layout)
        layout.addWidget(capital_group)

        # Strategy selection
        strategy_group = QGroupBox("Strategy")
        strategy_layout = QVBoxLayout()

        self.use_active_strategy = QCheckBox("Use currently active strategy")
        self.use_active_strategy.setChecked(True)
        strategy_layout.addWidget(self.use_active_strategy)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(self.strategy_manager.list_strategies())
        self.strategy_combo.setEnabled(False)
        strategy_layout.addWidget(self.strategy_combo)

        # Connect checkbox
        self.use_active_strategy.toggled.connect(
            lambda checked: self.strategy_combo.setEnabled(not checked)
        )

        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # Option settings
        option_group = QGroupBox("Option Settings")
        option_layout = QFormLayout()

        self.option_type = QComboBox()
        self.option_type.addItems(["BOTH", "CE", "PE"])
        option_layout.addRow("Option Type:", self.option_type)

        self.expiry_week = QSpinBox()
        self.expiry_week.setRange(0, 3)
        self.expiry_week.setValue(0)
        self.expiry_week.setToolTip("0 = current week, 1 = next week, etc.")
        option_layout.addRow("Expiry Week:", self.expiry_week)

        option_group.setLayout(option_layout)
        layout.addWidget(option_group)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.run_btn = QPushButton("▶ Run Backtest")
        # Styled via apply_theme()
        btn_layout.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setVisible(False)
        # Styled via apply_theme()
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("💾 Save Results")
        self.save_btn.setEnabled(False)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def _create_results_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.tabs = QTabWidget()

        # Summary tab
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.summary_text, "📊 Summary")

        # Trades tab
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(9)
        self.trades_table.setHorizontalHeaderLabels([
            "Entry Time", "Exit Time", "Position", "Qty",
            "Entry Price", "Exit Price", "PnL", "PnL %", "Exit Reason"
        ])
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        self.trades_table.setAlternatingRowColors(True)
        self.tabs.addTab(self.trades_table, "📋 Trades")

        # Equity curve tab
        self.equity_chart_view = QChartView()
        self.equity_chart_view.setRenderHint(QPainter.Antialiasing)
        self.tabs.addTab(self.equity_chart_view, "📈 Equity Curve")

        layout.addWidget(self.tabs)

        return widget

    def _connect_signals(self):
        self.run_btn.clicked.connect(self._run_backtest)
        self.cancel_btn.clicked.connect(self._cancel_backtest)
        self.save_btn.clicked.connect(self._save_results)

    def _run_backtest(self):
        """Start backtest in worker thread."""
        # Validate inputs
        if self.start_date.date() >= self.end_date.date():
            QMessageBox.warning(self, "Invalid Dates", "Start date must be before end date.")
            return

        # Prepare parameters
        params = {
            'symbol': self.symbol_combo.currentText(),
            'start_date': self.start_date.date().toString("yyyy-MM-dd"),
            'end_date': self.end_date.date().toString("yyyy-MM-dd"),
            'interval': self.interval_combo.currentText(),
            'initial_capital': self.initial_capital.value(),
            'lot_size': self.lot_size.value(),
            'option_type': self.option_type.currentText(),
            'expiry_week': self.expiry_week.value()
        }

        # Update UI state
        self.run_btn.setEnabled(False)
        self.run_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting backtest...")

        # Create and start worker
        self.worker = BacktestWorker(
            self.config,
            self.strategy_manager if self.use_active_strategy.isChecked() else None,
            params
        )

        self.worker.progress_updated.connect(self._on_progress)
        self.worker.status_updated.connect(self.status_label.setText)
        self.worker.result_ready.connect(self._on_result)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.finished.connect(self._on_worker_finished)

        self.worker.start()

    def _cancel_backtest(self):
        """Cancel running backtest."""
        if self.worker:
            self.worker.cancel()
            self.status_label.setText("Cancelling...")

    def _on_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def _on_result(self, result: BacktestResult):
        """Handle backtest result."""
        self.current_result = result
        self._display_results(result)
        self.save_btn.setEnabled(True)

    def _on_error(self, error_msg: str):
        QMessageBox.critical(self, "Backtest Error", f"Error running backtest:\n{error_msg}")

    def _on_worker_finished(self):
        """Clean up after worker finishes."""
        self.run_btn.setEnabled(True)
        self.run_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ready")
        self.worker = None

    def _display_results(self, result: BacktestResult):
        """Display backtest results in UI."""

        # Summary tab
        summary = f"""
╔══════════════════════════════════════════════════════════════╗
║                    BACKTEST SUMMARY                          ║
╠══════════════════════════════════════════════════════════════╣
║  Period:     {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}
║  Duration:   {(result.end_date - result.start_date).days} days
╠══════════════════════════════════════════════════════════════╣
║  Initial Capital:  ₹ {result.initial_capital:,.2f}
║  Final Capital:    ₹ {result.final_capital:,.2f}
║  Total P&L:        ₹ {result.total_pnl:,.2f} ({result.total_pnl_percent:.2f}%)
╠══════════════════════════════════════════════════════════════╣
║  Total Trades:     {result.total_trades}
║  Winning Trades:   {result.winning_trades}
║  Losing Trades:    {result.losing_trades}
║  Win Rate:         {result.win_rate * 100:.1f}%
╠══════════════════════════════════════════════════════════════╣
║  Avg Win:          ₹ {result.avg_win:,.2f}
║  Avg Loss:         ₹ {result.avg_loss:,.2f}
║  Max Drawdown:     ₹ {result.max_drawdown:,.2f} ({result.max_drawdown_percent:.2f}%)
║  Sharpe Ratio:     {result.sharpe_ratio:.3f}
╚══════════════════════════════════════════════════════════════╝
        """
        self.summary_text.setText(summary)

        # Trades tab
        self.trades_table.setRowCount(len(result.trades))
        for i, trade in enumerate(result.trades):
            self.trades_table.setItem(i, 0, QTableWidgetItem(trade.entry_time.strftime('%Y-%m-%d %H:%M')))
            self.trades_table.setItem(i, 1, QTableWidgetItem(
                trade.exit_time.strftime('%Y-%m-%d %H:%M') if trade.exit_time else "Open"
            ))
            self.trades_table.setItem(i, 2, QTableWidgetItem(trade.position or ""))
            self.trades_table.setItem(i, 3, QTableWidgetItem(str(trade.qty)))
            self.trades_table.setItem(i, 4, QTableWidgetItem(f"₹ {trade.entry_price:.2f}" if trade.entry_price else ""))
            self.trades_table.setItem(i, 5, QTableWidgetItem(f"₹ {trade.exit_price:.2f}" if trade.exit_price else ""))

            pnl_item = QTableWidgetItem(f"₹ {trade.pnl:.2f}")
            if trade.pnl > 0:
                pnl_item.setForeground(QColor(theme_manager.palette.GREEN))
            elif trade.pnl < 0:
                pnl_item.setForeground(QColor(theme_manager.palette.RED))
            self.trades_table.setItem(i, 6, pnl_item)

            pnl_pct_item = QTableWidgetItem(f"{trade.pnl_percent:.2f}%")
            if trade.pnl_percent > 0:
                pnl_pct_item.setForeground(QColor(theme_manager.palette.GREEN))
            elif trade.pnl_percent < 0:
                pnl_pct_item.setForeground(QColor(theme_manager.palette.RED))
            self.trades_table.setItem(i, 7, pnl_pct_item)

            self.trades_table.setItem(i, 8, QTableWidgetItem(trade.exit_reason or ""))

        self.trades_table.resizeColumnsToContents()

        # Equity curve
        self._plot_equity_curve(result)

    def _plot_equity_curve(self, result: BacktestResult):
        """Plot equity curve using QChart."""
        chart = QChart()
        chart.setTitle("Equity Curve")
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setTheme(QChart.ChartThemeDark)

        # Create series
        series = QLineSeries()
        series.setName("Equity")

        for i, value in enumerate(result.equity_curve):
            series.append(i, value)

        chart.addSeries(series)

        # Create axes
        axis_x = QValueAxis()
        axis_x.setTitleText("Bar")
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setTitleText("Capital (₹)")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        # Add reference line for initial capital
        import_lines = QLineSeries()
        import_lines.setName("Initial Capital")
        import_lines.append(0, result.initial_capital)
        import_lines.append(len(result.equity_curve) - 1, result.initial_capital)
        import_lines.setColor(QColor(theme_manager.palette.TEXT_DIM))
        import_lines.setStyle(Qt.DashLine)
        chart.addSeries(import_lines)
        import_lines.attachAxis(axis_x)
        import_lines.attachAxis(axis_y)

        self.equity_chart_view.setChart(chart)

    def _save_results(self):
        """Save backtest results to file."""
        if not self.current_result:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backtest Results",
            f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "JSON Files (*.json)"
        )

        if filename:
            engine = BacktestEngine(self.config, self.strategy_manager)
            engine.save_results(self.current_result, filename.replace('.json', ''))
            QMessageBox.information(self, "Saved", f"Results saved to {filename}")