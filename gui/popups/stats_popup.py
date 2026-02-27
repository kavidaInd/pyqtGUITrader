"""
stats_popup.py
==============
Popup window for displaying trading statistics with multiple tabs.
"""

import logging
import logging.handlers
import traceback
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel, QTabWidget, QHBoxLayout

# Rule 4: Structured logging
logger = logging.getLogger(__name__)


class StatsPopup(QDialog):
    """Popup window for displaying statistics with multiple tabs"""

    def __init__(self, state, parent=None):
        # Rule 2: Safe defaults first
        self._safe_defaults_init()

        try:
            super().__init__(parent)
            self.state = state
            self.setWindowTitle("📊 Trading Statistics")
            self.resize(1000, 750)
            self.setMinimumSize(800, 600)

            # Set window flags to make it a proper popup
            self.setWindowFlags(Qt.Window)

            # EXACT stylesheet preservation with enhancements
            self.setStyleSheet("""
                QDialog { 
                    background: #0d1117; 
                    color: #e6edf3; 
                }
                QTabWidget::pane { 
                    border: 1px solid #30363d; 
                    background: #0d1117;
                }
                QTabBar::tab { 
                    background: #161b22; 
                    color: #8b949e;
                    padding: 8px 16px; 
                    border: 1px solid #30363d; 
                    margin-right: 2px;
                }
                QTabBar::tab:selected { 
                    background: #21262d; 
                    color: #e6edf3;
                    border-bottom: 2px solid #58a6ff; 
                }
                QTabBar::tab:hover {
                    background: #21262d;
                }
                QLabel { 
                    color: #e6edf3; 
                    font-size: 10pt; 
                }
                QLabel[cssClass="value"] { 
                    color: #58a6ff; 
                    font-weight: bold; 
                }
                QLabel[cssClass="positive"] { 
                    color: #3fb950; 
                }
                QLabel[cssClass="negative"] { 
                    color: #f85149; 
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
                QPushButton {
                    background: #21262d;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-weight: bold;
                    min-width: 100px;
                }
                QPushButton:hover { 
                    background: #30363d; 
                }
                QPushButton:pressed {
                    background: #3d444d;
                }
                QPushButton#closeBtn {
                    background: #da3633;
                }
                QPushButton#closeBtn:hover {
                    background: #f85149;
                }
                QScrollArea {
                    border: 1px solid #30363d;
                    background: #0d1117;
                }
                QTableWidget {
                    background: #161b22;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    gridline-color: #30363d;
                }
                QTableWidget::item {
                    padding: 4px;
                }
                QHeaderView::section {
                    background: #21262d;
                    color: #8b949e;
                    border: none;
                    border-bottom: 1px solid #30363d;
                    padding: 4px;
                }
            """)

            # Main layout
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)

            # Create tab widget
            self.tab_widget = QTabWidget()

            # Import StatsTab and add it
            try:
                from gui.stats_tab import StatsTab
                self.stats_tab = StatsTab(self.state)
                self.tab_widget.addTab(self.stats_tab, "📈 Overview")

                # FEATURE 1: Add risk tab if available in state
                if hasattr(self.state, 'get_risk_summary'):
                    self._add_risk_tab()

                # FEATURE 6: Add MTF tab
                self._add_mtf_tab()

                # FEATURE 3: Add signal confidence tab
                self._add_signal_confidence_tab()

            except ImportError as e:
                logger.error(f"Failed to import StatsTab: {e}", exc_info=True)
                # Add error message to layout
                error_label = QLabel(f"❌ Failed to load statistics tab: {e}")
                error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
                error_label.setWordWrap(True)
                layout.addWidget(error_label)
                self.stats_tab = None
            except Exception as e:
                logger.error(f"Failed to create StatsTab: {e}", exc_info=True)
                error_label = QLabel(f"❌ Failed to create statistics tab: {e}")
                error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
                error_label.setWordWrap(True)
                layout.addWidget(error_label)
                self.stats_tab = None

            # Add tab widget to layout
            if self.tab_widget.count() > 0:
                layout.addWidget(self.tab_widget, 1)

            # Refresh timer
            self.refresh_timer = QTimer(self)
            self.refresh_timer.timeout.connect(self.refresh)
            self.refresh_timer.start(2000)  # Refresh every 2 seconds

            # Button bar
            button_layout = QVBoxLayout()

            # Refresh button
            refresh_btn = QPushButton("⟳ Refresh Now")
            refresh_btn.clicked.connect(self.refresh)
            button_layout.addWidget(refresh_btn)

            # Close button
            close_btn = QPushButton("✕ Close")
            close_btn.setObjectName("closeBtn")
            close_btn.clicked.connect(self.accept)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            logger.info("StatsPopup initialized successfully")

        except Exception as e:
            logger.critical(f"[StatsPopup.__init__] Failed: {e}", exc_info=True)
            self._create_error_dialog(parent)

    def _add_risk_tab(self):
        """
        FEATURE 1: Add risk statistics tab.
        """
        try:
            from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QGroupBox

            risk_widget = QWidget()
            layout = QVBoxLayout(risk_widget)

            # Daily limits group
            limits_group = QGroupBox("Daily Risk Limits")
            limits_layout = QGridLayout()

            self.risk_labels = {}

            # Max daily loss
            limits_layout.addWidget(QLabel("Max Daily Loss:"), 0, 0)
            self.risk_labels['max_loss'] = QLabel("₹-5,000")
            self.risk_labels['max_loss'].setProperty("cssClass", "value")
            limits_layout.addWidget(self.risk_labels['max_loss'], 0, 1)

            # Current P&L
            limits_layout.addWidget(QLabel("Current P&L:"), 1, 0)
            self.risk_labels['current_pnl'] = QLabel("₹0.00")
            self.risk_labels['current_pnl'].setProperty("cssClass", "value")
            limits_layout.addWidget(self.risk_labels['current_pnl'], 1, 1)

            # Remaining loss
            limits_layout.addWidget(QLabel("Loss Remaining:"), 2, 0)
            self.risk_labels['loss_remaining'] = QLabel("₹5,000")
            self.risk_labels['loss_remaining'].setProperty("cssClass", "value")
            limits_layout.addWidget(self.risk_labels['loss_remaining'], 2, 1)

            # Max trades
            limits_layout.addWidget(QLabel("Max Trades/Day:"), 3, 0)
            self.risk_labels['max_trades'] = QLabel("10")
            self.risk_labels['max_trades'].setProperty("cssClass", "value")
            limits_layout.addWidget(self.risk_labels['max_trades'], 3, 1)

            # Trades today
            limits_layout.addWidget(QLabel("Trades Today:"), 4, 0)
            self.risk_labels['trades_today'] = QLabel("0")
            self.risk_labels['trades_today'].setProperty("cssClass", "value")
            limits_layout.addWidget(self.risk_labels['trades_today'], 4, 1)

            # Trades remaining
            limits_layout.addWidget(QLabel("Trades Remaining:"), 5, 0)
            self.risk_labels['trades_remaining'] = QLabel("10")
            self.risk_labels['trades_remaining'].setProperty("cssClass", "value")
            limits_layout.addWidget(self.risk_labels['trades_remaining'], 5, 1)

            # Blocked status
            limits_layout.addWidget(QLabel("Risk Blocked:"), 6, 0)
            self.risk_labels['risk_blocked'] = QLabel("No")
            self.risk_labels['risk_blocked'].setProperty("cssClass", "positive")
            limits_layout.addWidget(self.risk_labels['risk_blocked'], 6, 1)

            limits_group.setLayout(limits_layout)
            layout.addWidget(limits_group)

            # Stats group
            stats_group = QGroupBox("Daily Statistics")
            stats_layout = QGridLayout()

            # Win rate
            stats_layout.addWidget(QLabel("Win Rate:"), 0, 0)
            self.risk_labels['win_rate'] = QLabel("0%")
            self.risk_labels['win_rate'].setProperty("cssClass", "value")
            stats_layout.addWidget(self.risk_labels['win_rate'], 0, 1)

            # Winners
            stats_layout.addWidget(QLabel("Winners:"), 1, 0)
            self.risk_labels['winners'] = QLabel("0")
            self.risk_labels['winners'].setProperty("cssClass", "positive")
            stats_layout.addWidget(self.risk_labels['winners'], 1, 1)

            # Losers
            stats_layout.addWidget(QLabel("Losers:"), 2, 0)
            self.risk_labels['losers'] = QLabel("0")
            self.risk_labels['losers'].setProperty("cssClass", "negative")
            stats_layout.addWidget(self.risk_labels['losers'], 2, 1)

            stats_group.setLayout(stats_layout)
            layout.addWidget(stats_group)

            layout.addStretch()

            self.tab_widget.addTab(risk_widget, "⚠️ Risk")

        except Exception as e:
            logger.error(f"[StatsPopup._add_risk_tab] Failed: {e}", exc_info=True)

    def _add_mtf_tab(self):
        """
        FEATURE 6: Add Multi-Timeframe Filter statistics tab.
        """
        try:
            from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QGroupBox

            mtf_widget = QWidget()
            layout = QVBoxLayout(mtf_widget)

            # Status group
            status_group = QGroupBox("MTF Filter Status")
            status_layout = QGridLayout()

            # Enabled status
            status_layout.addWidget(QLabel("Enabled:"), 0, 0)
            self.mtf_labels = {}
            self.mtf_labels['enabled'] = QLabel("No")
            self.mtf_labels['enabled'].setProperty("cssClass", "value")
            status_layout.addWidget(self.mtf_labels['enabled'], 0, 1)

            # Current signal
            status_layout.addWidget(QLabel("Current Signal:"), 1, 0)
            self.mtf_labels['signal'] = QLabel("WAIT")
            self.mtf_labels['signal'].setProperty("cssClass", "value")
            status_layout.addWidget(self.mtf_labels['signal'], 1, 1)

            status_group.setLayout(status_layout)
            layout.addWidget(status_group)

            # Timeframe directions
            tf_group = QGroupBox("Timeframe Directions")
            tf_layout = QGridLayout()

            tf_layout.addWidget(QLabel("1 Minute:"), 0, 0)
            self.mtf_labels['1m'] = QLabel("NEUTRAL")
            self.mtf_labels['1m'].setProperty("cssClass", "value")
            tf_layout.addWidget(self.mtf_labels['1m'], 0, 1)

            tf_layout.addWidget(QLabel("5 Minute:"), 1, 0)
            self.mtf_labels['5m'] = QLabel("NEUTRAL")
            self.mtf_labels['5m'].setProperty("cssClass", "value")
            tf_layout.addWidget(self.mtf_labels['5m'], 1, 1)

            tf_layout.addWidget(QLabel("15 Minute:"), 2, 0)
            self.mtf_labels['15m'] = QLabel("NEUTRAL")
            self.mtf_labels['15m'].setProperty("cssClass", "value")
            tf_layout.addWidget(self.mtf_labels['15m'], 2, 1)

            # Agreement
            tf_layout.addWidget(QLabel("Agreement:"), 3, 0)
            self.mtf_labels['agreement'] = QLabel("0/3")
            self.mtf_labels['agreement'].setProperty("cssClass", "value")
            tf_layout.addWidget(self.mtf_labels['agreement'], 3, 1)

            tf_group.setLayout(tf_layout)
            layout.addWidget(tf_group)

            # Last decision
            decision_group = QGroupBox("Last Decision")
            decision_layout = QVBoxLayout()

            self.mtf_labels['decision'] = QLabel("No decision yet")
            self.mtf_labels['decision'].setWordWrap(True)
            self.mtf_labels['decision'].setStyleSheet("color: #8b949e; font-size: 10pt;")
            decision_layout.addWidget(self.mtf_labels['decision'])

            decision_group.setLayout(decision_layout)
            layout.addWidget(decision_group)

            layout.addStretch()

            self.tab_widget.addTab(mtf_widget, "📈 MTF Filter")

        except Exception as e:
            logger.error(f"[StatsPopup._add_mtf_tab] Failed: {e}", exc_info=True)

    def _add_signal_confidence_tab(self):
        """
        FEATURE 3: Add signal confidence statistics tab.
        """
        try:
            from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QGroupBox, QProgressBar

            conf_widget = QWidget()
            layout = QVBoxLayout(conf_widget)

            self.conf_labels = {}
            self.conf_bars = {}

            # Signal groups
            signal_groups = ['BUY_CALL', 'BUY_PUT', 'EXIT_CALL', 'EXIT_PUT', 'HOLD']

            for signal in signal_groups:
                group = QGroupBox(signal.replace('_', ' '))
                group_layout = QVBoxLayout()

                # Confidence bar
                bar_layout = QHBoxLayout()
                bar_layout.addWidget(QLabel("Confidence:"))

                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFormat("%p%")
                bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #30363d;
                        border-radius: 4px;
                        text-align: center;
                        color: #e6edf3;
                    }
                    QProgressBar::chunk {
                        background: #58a6ff;
                        border-radius: 4px;
                    }
                """)
                bar_layout.addWidget(bar)

                group_layout.addLayout(bar_layout)

                # Threshold indicator
                threshold_layout = QHBoxLayout()
                threshold_layout.addWidget(QLabel("Threshold:"))
                threshold_label = QLabel("60%")
                threshold_label.setProperty("cssClass", "value")
                threshold_layout.addWidget(threshold_label)
                threshold_layout.addStretch()
                group_layout.addLayout(threshold_layout)

                group.setLayout(group_layout)
                layout.addWidget(group)

                self.conf_labels[signal] = threshold_label
                self.conf_bars[signal] = bar

            # Explanation group
            exp_group = QGroupBox("Signal Explanation")
            exp_layout = QVBoxLayout()

            self.conf_explanation = QLabel("No signal evaluation yet")
            self.conf_explanation.setWordWrap(True)
            self.conf_explanation.setStyleSheet("color: #8b949e; font-size: 10pt; padding: 8px;")
            exp_layout.addWidget(self.conf_explanation)

            exp_group.setLayout(exp_layout)
            layout.addWidget(exp_group)

            layout.addStretch()

            self.tab_widget.addTab(conf_widget, "🎯 Signal Confidence")

        except Exception as e:
            logger.error(f"[StatsPopup._add_signal_confidence_tab] Failed: {e}", exc_info=True)

    def _create_error_dialog(self, parent):
        """Create error dialog if initialization fails"""
        try:
            super().__init__(parent)
            self.setWindowTitle("Statistics - ERROR")
            self.resize(400, 300)

            layout = QVBoxLayout(self)
            error_label = QLabel("❌ Failed to initialize statistics popup. Please check logs.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #f85149; padding: 20px; font-size: 12pt;")
            layout.addWidget(error_label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"[StatsPopup._create_error_dialog] Failed: {e}", exc_info=True)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.state = None
        self.stats_tab = None
        self.refresh_timer = None
        self.tab_widget = None
        self.risk_labels = {}
        self.mtf_labels = {}
        self.conf_labels = {}
        self.conf_bars = {}
        self.conf_explanation = None

    def refresh(self):
        """Refresh all statistics tabs"""
        try:
            # Rule 6: Check if we should refresh
            if self.state is None:
                logger.debug("refresh called with None state")
                return

            # Refresh main stats tab
            if self.stats_tab is not None:
                try:
                    if hasattr(self.stats_tab, 'refresh') and callable(self.stats_tab.refresh):
                        self.stats_tab.refresh()
                except Exception as e:
                    logger.error(f"Failed to refresh stats tab: {e}", exc_info=True)

            # FEATURE 1: Refresh risk tab
            self._refresh_risk_tab()

            # FEATURE 6: Refresh MTF tab
            self._refresh_mtf_tab()

            # FEATURE 3: Refresh signal confidence tab
            self._refresh_confidence_tab()

            logger.debug("Statistics refreshed")

        except Exception as e:
            logger.error(f"[StatsPopup.refresh] Failed: {e}", exc_info=True)

    def _refresh_risk_tab(self):
        """Refresh risk statistics tab"""
        try:
            if not hasattr(self, 'risk_labels') or not self.risk_labels:
                return

            # Get risk summary from state if available
            risk_summary = {}
            if hasattr(self.state, 'get_risk_summary'):
                try:
                    risk_summary = self.state.get_risk_summary(self.state)
                except:
                    pass

            # Update labels with fallbacks
            self._update_label(self.risk_labels, 'max_loss',
                               f"₹{risk_summary.get('max_loss', -5000):,.0f}")
            self._update_label(self.risk_labels, 'current_pnl',
                               f"₹{risk_summary.get('pnl_today', 0):,.2f}")
            self._update_label(self.risk_labels, 'loss_remaining',
                               f"₹{risk_summary.get('max_loss_remaining', 5000):,.2f}")
            self._update_label(self.risk_labels, 'max_trades',
                               str(risk_summary.get('max_trades', 10)))
            self._update_label(self.risk_labels, 'trades_today',
                               str(risk_summary.get('trades_today', 0)))
            self._update_label(self.risk_labels, 'trades_remaining',
                               str(risk_summary.get('max_trades_remaining', 10)))

            # Blocked status
            is_blocked = risk_summary.get('is_blocked', False)
            self._update_label(self.risk_labels, 'risk_blocked',
                               "Yes" if is_blocked else "No",
                               "negative" if is_blocked else "positive")

            # Calculate win rate
            trades = risk_summary.get('trades_today', 0)
            pnl = risk_summary.get('pnl_today', 0)
            winners = sum(1 for _ in range(trades) if pnl > 0)  # Simplified
            losers = trades - winners
            win_rate = (winners / trades * 100) if trades > 0 else 0

            self._update_label(self.risk_labels, 'win_rate', f"{win_rate:.0f}%")
            self._update_label(self.risk_labels, 'winners', str(winners))
            self._update_label(self.risk_labels, 'losers', str(losers))

        except Exception as e:
            logger.error(f"[StatsPopup._refresh_risk_tab] Failed: {e}", exc_info=True)

    def _refresh_mtf_tab(self):
        """Refresh MTF filter tab"""
        try:
            if not hasattr(self, 'mtf_labels') or not self.mtf_labels:
                return

            # Get MTF results from state
            mtf_results = {}
            if self.state and hasattr(self.state, 'mtf_results'):
                mtf_results = self.state.mtf_results

            # Update timeframe directions
            self._update_label(self.mtf_labels, '1m', mtf_results.get('1', 'NEUTRAL'))
            self._update_label(self.mtf_labels, '5m', mtf_results.get('5', 'NEUTRAL'))
            self._update_label(self.mtf_labels, '15m', mtf_results.get('15', 'NEUTRAL'))

            # Count agreement
            target = 'BULLISH' if getattr(self.state, 'option_signal', '') == 'BUY_CALL' else 'BEARISH'
            matches = sum(1 for d in mtf_results.values() if d == target)
            self._update_label(self.mtf_labels, 'agreement', f"{matches}/3")

            # Update enabled status
            enabled = False
            if self.state and hasattr(self.state, 'mtf_allowed'):
                enabled = self.state.mtf_allowed
            self._update_label(self.mtf_labels, 'enabled', "Yes" if enabled else "No")

            # Update signal
            signal = getattr(self.state, 'option_signal', 'WAIT')
            self._update_label(self.mtf_labels, 'signal', signal)

            # Update decision
            if self.state and hasattr(self.state, 'last_mtf_summary'):
                self._update_label(self.mtf_labels, 'decision', self.state.last_mtf_summary or "No decision yet")

        except Exception as e:
            logger.error(f"[StatsPopup._refresh_mtf_tab] Failed: {e}", exc_info=True)

    def _refresh_confidence_tab(self):
        """Refresh signal confidence tab"""
        try:
            if not hasattr(self, 'conf_labels') or not self.conf_labels:
                return

            # Get confidence from state
            confidence = {}
            explanation = ""
            threshold = 0.6

            if self.state:
                if hasattr(self.state, 'signal_confidence'):
                    confidence = self.state.signal_confidence
                if hasattr(self.state, 'signal_explanation'):
                    explanation = self.state.signal_explanation
                if hasattr(self.state, 'option_signal_result'):
                    result = self.state.option_signal_result
                    if result:
                        threshold = result.get('threshold', 0.6)

            # Update confidence bars
            for signal, bar in self.conf_bars.items():
                conf = confidence.get(signal, 0.0) * 100
                bar.setValue(int(conf))

                # Color based on threshold
                if conf >= threshold * 100:
                    bar.setStyleSheet("""
                        QProgressBar::chunk { background: #3fb950; }
                    """)
                elif conf >= threshold * 70:
                    bar.setStyleSheet("""
                        QProgressBar::chunk { background: #d29922; }
                    """)
                else:
                    bar.setStyleSheet("""
                        QProgressBar::chunk { background: #f85149; }
                    """)

            # Update threshold labels
            threshold_pct = int(threshold * 100)
            for label in self.conf_labels.values():
                label.setText(f"{threshold_pct}%")

            # Update explanation
            if self.conf_explanation:
                self.conf_explanation.setText(explanation or "No signal evaluation yet")

        except Exception as e:
            logger.error(f"[StatsPopup._refresh_confidence_tab] Failed: {e}", exc_info=True)

    def _update_label(self, label_dict, key, value, css_class="value"):
        """Helper to update a label with error handling"""
        try:
            if key in label_dict and label_dict[key] is not None:
                label_dict[key].setText(value)
                label_dict[key].setProperty("cssClass", css_class)
                # Force style refresh
                label_dict[key].style().unpolish(label_dict[key])
                label_dict[key].style().polish(label_dict[key])
        except Exception as e:
            logger.debug(f"Failed to update label {key}: {e}")

    # Rule 8: Cleanup method
    def cleanup(self):
        """Clean up resources before closing"""
        try:
            logger.info("[StatsPopup] Starting cleanup")

            # Stop timer
            if self.refresh_timer is not None:
                try:
                    if self.refresh_timer.isActive():
                        self.refresh_timer.stop()
                    self.refresh_timer = None
                except Exception as e:
                    logger.warning(f"Error stopping timer: {e}")

            # Clear stats tab
            if self.stats_tab is not None:
                try:
                    if hasattr(self.stats_tab, 'cleanup'):
                        self.stats_tab.cleanup()
                except Exception as e:
                    logger.warning(f"Error cleaning up stats tab: {e}")
                self.stats_tab = None

            # Clear references
            self.state = None
            self.tab_widget = None
            self.risk_labels.clear()
            self.mtf_labels.clear()
            self.conf_labels.clear()
            self.conf_bars.clear()
            self.conf_explanation = None
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