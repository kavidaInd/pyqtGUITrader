"""
backtest/backtest_help_tab.py
==============================
Comprehensive Help & Documentation tab for the Backtest Window.
Provides detailed guidance on backtesting concepts, configuration,
interpreting results, and troubleshooting.

FEATURES:
- Interactive documentation with examples
- Searchable navigation tree
- Configuration guides
- Results interpretation
- Troubleshooting guides
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFont, QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QStackedWidget, QTextEdit,
    QPushButton, QLineEdit, QSplitter, QScrollArea, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox
)

logger = logging.getLogger(__name__)

# ── Color Palette (matching backtest window) ─────────────────────────────────
BG = "#0d1117"
BG_PANEL = "#161b22"
BG_ITEM = "#1c2128"
BG_SEL = "#1f3d5c"
BORDER = "#30363d"
TEXT = "#e6edf3"
DIM = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BLUE = "#58a6ff"
YELLOW = "#d29922"
ORANGE = "#ffa657"
PURPLE = "#bc8cff"
ACCENT = "#2ea043"
WARN = "#d29922"
ERROR_C = "#f85149"
INFO = "#58a6ff"
CALL_CLR = "#3fb950"
PUT_CLR = "#f85149"
SYNTH_BG = "#2d2a1a"


class BacktestHelpTab(QWidget):
    """
    Comprehensive help and documentation tab for the Backtest Window.
    Provides guidance on backtesting concepts, configuration, and results.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pages = {}
        self.nav_tree = None
        self.content_stack = None
        self.search_box = None

        self._init_ui()
        self._connect_navigation()
        self.show_page("welcome")

        logger.info("BacktestHelpTab initialized")

    def _init_ui(self):
        """Initialize the UI"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {BORDER};
            }}
        """)

        # Left navigation panel
        nav_widget = self._create_navigation_panel()
        splitter.addWidget(nav_widget)

        # Right content panel (stacked)
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet(f"""
            QStackedWidget {{
                background: {BG_PANEL};
                border-left: 1px solid {BORDER};
            }}
        """)

        # Create all content pages
        self._create_all_pages()

        splitter.addWidget(self.content_stack)
        splitter.setSizes([280, 720])  # 28% navigation, 72% content

        main_layout.addWidget(splitter)

    def _create_navigation_panel(self) -> QWidget:
        """Create the left navigation tree"""
        widget = QWidget()
        widget.setStyleSheet(f"background: {BG_PANEL};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QLabel("📚 BACKTEST HELP & DOCUMENTATION")
        header.setStyleSheet(f"color:{BLUE}; font-size:12pt; font-weight:bold; padding:10px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Search box
        search_layout = QHBoxLayout()
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(f"color:{DIM};")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search help...")
        self.search_box.textChanged.connect(self._filter_navigation)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)

        # Navigation tree
        self.nav_tree = QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setIndentation(15)
        self.nav_tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
            QTreeWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {BORDER}40;
            }}
            QTreeWidget::item:selected {{
                background: {BG_SEL};
                color: {BLUE};
            }}
        """)

        self._populate_navigation()
        layout.addWidget(self.nav_tree)

        # Quick links at bottom
        quick_links = QFrame()
        quick_links.setStyleSheet(f"border-top: 1px solid {BORDER}; margin-top: 10px;")
        links_layout = QVBoxLayout(quick_links)

        online_docs = QPushButton("🌐 Online Documentation")
        online_docs.clicked.connect(lambda: QMessageBox.information(
            self, "Coming Soon", "Online documentation will be available in a future update."))
        links_layout.addWidget(online_docs)

        export_guide = QPushButton("📥 Export Guide as PDF")
        export_guide.clicked.connect(lambda: QMessageBox.information(
            self, "Coming Soon", "PDF export will be available in a future update."))
        links_layout.addWidget(export_guide)

        report_issue = QPushButton("🐛 Report Issue")
        report_issue.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/yourusername/TradingGUI/issues/new")))
        links_layout.addWidget(report_issue)

        layout.addWidget(quick_links)

        return widget

    def _populate_navigation(self):
        """Populate the navigation tree with help topics"""
        # Welcome/Getting Started
        welcome = QTreeWidgetItem(["🏠 Welcome & Overview"])
        welcome.addChild(QTreeWidgetItem(["📋 What is Backtesting?"]))
        welcome.addChild(QTreeWidgetItem(["🚀 Quick Start Guide"]))
        welcome.addChild(QTreeWidgetItem(["⚙️ First-Time Setup"]))
        welcome.addChild(QTreeWidgetItem(["📊 Understanding the Interface"]))
        self.nav_tree.addTopLevelItem(welcome)

        # Configuration Guide
        config = QTreeWidgetItem(["⚙️ Configuration Guide"])
        config.addChild(QTreeWidgetItem(["📋 Strategy Tab"]))
        config.addChild(QTreeWidgetItem(["⏱ Timeframes Tab"]))
        config.addChild(QTreeWidgetItem(["📊 Instrument Tab"]))
        config.addChild(QTreeWidgetItem(["🛡 Risk Tab"]))
        config.addChild(QTreeWidgetItem(["💰 Costs Tab"]))
        config.addChild(QTreeWidgetItem(["⚙ Execution Tab"]))
        config.addChild(QTreeWidgetItem(["🎯 Complete Walkthrough"]))
        self.nav_tree.addTopLevelItem(config)

        # Backtest Concepts
        concepts = QTreeWidgetItem(["🧠 Backtest Concepts"])
        concepts.addChild(QTreeWidgetItem(["📈 Spot Data & Resampling"]))
        concepts.addChild(QTreeWidgetItem(["📊 Option Pricing"]))
        concepts.addChild(QTreeWidgetItem(["⚗️ Synthetic vs Real Data"]))
        concepts.addChild(QTreeWidgetItem(["🎯 Entry & Exit Logic"]))
        concepts.addChild(QTreeWidgetItem(["⚖️ Position Management"]))
        concepts.addChild(QTreeWidgetItem(["⏱️ Multi-Timeframe Analysis"]))
        concepts.addChild(QTreeWidgetItem(["📉 Equity Curves"]))
        self.nav_tree.addTopLevelItem(concepts)

        # Results Interpretation
        results = QTreeWidgetItem(["📊 Results Interpretation"])
        results.addChild(QTreeWidgetItem(["📈 Overview Tab"]))
        results.addChild(QTreeWidgetItem(["📋 Trade Log Tab"]))
        results.addChild(QTreeWidgetItem(["🔬 Strategy Analysis Tab"]))
        results.addChild(QTreeWidgetItem(["📉 Equity Curve Tab"]))
        results.addChild(QTreeWidgetItem(["🔍 Candle Debug Tab"]))
        results.addChild(QTreeWidgetItem(["📊 Understanding Metrics"]))
        results.addChild(QTreeWidgetItem(["📈 Reading Equity Curves"]))
        self.nav_tree.addTopLevelItem(results)

        # Option Pricing
        pricing = QTreeWidgetItem(["💰 Option Pricing"])
        pricing.addChild(QTreeWidgetItem(["📈 Black-Scholes Model"]))
        pricing.addChild(QTreeWidgetItem(["🌪️ Volatility Sources"]))
        pricing.addChild(QTreeWidgetItem(["📊 VIX vs Historical Volatility"]))
        pricing.addChild(QTreeWidgetItem(["📅 Expiry Calculation"]))
        pricing.addChild(QTreeWidgetItem(["⚗️ Synthetic Price Generation"]))
        pricing.addChild(QTreeWidgetItem(["✅ Real Data Priority"]))
        self.nav_tree.addTopLevelItem(pricing)

        # Risk Management
        risk = QTreeWidgetItem(["🛡️ Risk Management"])
        risk.addChild(QTreeWidgetItem(["🎯 Take Profit (TP)"]))
        risk.addChild(QTreeWidgetItem(["🛑 Stop Loss (SL)"]))
        risk.addChild(QTreeWidgetItem(["🏃 Trailing Stop Loss"]))
        risk.addChild(QTreeWidgetItem(["📉 Index-Based Stop Loss"]))
        risk.addChild(QTreeWidgetItem(["⏱️ Max Hold Bars"]))
        risk.addChild(QTreeWidgetItem(["📊 Risk-Reward Ratios"]))
        risk.addChild(QTreeWidgetItem(["⏸️ Sideway Zone Skip"]))
        self.nav_tree.addTopLevelItem(risk)

        # Costs & Execution
        costs = QTreeWidgetItem(["💰 Costs & Execution"])
        costs.addChild(QTreeWidgetItem(["📉 Slippage"]))
        costs.addChild(QTreeWidgetItem(["💸 Brokerage"]))
        costs.addChild(QTreeWidgetItem(["📊 Position Sizing"]))
        costs.addChild(QTreeWidgetItem(["💵 Capital Management"]))
        costs.addChild(QTreeWidgetItem(["⚡ Execution Intervals"]))
        self.nav_tree.addTopLevelItem(costs)

        # Advanced Features
        advanced = QTreeWidgetItem(["🔬 Advanced Features"])
        advanced.addChild(QTreeWidgetItem(["📊 Multi-Timeframe Analysis"]))
        advanced.addChild(QTreeWidgetItem(["🔍 Candle Debugger"]))
        advanced.addChild(QTreeWidgetItem(["📤 Export Results"]))
        advanced.addChild(QTreeWidgetItem(["📥 Import Configurations"]))
        advanced.addChild(QTreeWidgetItem(["🔄 Batch Testing"]))
        self.nav_tree.addTopLevelItem(advanced)

        # Troubleshooting
        troubleshooting = QTreeWidgetItem(["🔧 Troubleshooting"])
        troubleshooting.addChild(QTreeWidgetItem(["❌ Common Errors"]))
        troubleshooting.addChild(QTreeWidgetItem(["🔍 Debugging Tips"]))
        troubleshooting.addChild(QTreeWidgetItem(["📊 Log Analysis"]))
        troubleshooting.addChild(QTreeWidgetItem(["⚠️ Performance Issues"]))
        troubleshooting.addChild(QTreeWidgetItem(["❓ FAQ"]))
        self.nav_tree.addTopLevelItem(troubleshooting)

        # Best Practices
        best_practices = QTreeWidgetItem(["✨ Best Practices"])
        best_practices.addChild(QTreeWidgetItem(["🎯 Setting Up Backtests"]))
        best_practices.addChild(QTreeWidgetItem(["📊 Avoiding Overfitting"]))
        best_practices.addChild(QTreeWidgetItem(["📈 Interpreting Results"]))
        best_practices.addChild(QTreeWidgetItem(["⚖️ Risk Management"]))
        best_practices.addChild(QTreeWidgetItem(["🔄 Iterative Improvement"]))
        best_practices.addChild(QTreeWidgetItem(["⚠️ Common Mistakes"]))
        self.nav_tree.addTopLevelItem(best_practices)

        # Keyboard Shortcuts
        shortcuts = QTreeWidgetItem(["⌨️ Keyboard Shortcuts"])
        self.nav_tree.addTopLevelItem(shortcuts)

        # Glossary
        glossary = QTreeWidgetItem(["📚 Glossary"])
        self.nav_tree.addTopLevelItem(glossary)

        # Expand all top-level items
        for i in range(self.nav_tree.topLevelItemCount()):
            self.nav_tree.topLevelItem(i).setExpanded(True)

    def _create_all_pages(self):
        """Create all content pages for the help system"""
        # Welcome Page
        self.pages["welcome"] = self._create_welcome_page()
        self.content_stack.addWidget(self.pages["welcome"])

        # Overview Pages
        self.pages["📋 What is Backtesting?"] = self._create_text_page(
            "📋 What is Backtesting?",
            self._get_backtesting_overview_content()
        )
        self.content_stack.addWidget(self.pages["📋 What is Backtesting?"])

        self.pages["🚀 Quick Start Guide"] = self._create_quick_start_page()
        self.content_stack.addWidget(self.pages["🚀 Quick Start Guide"])

        self.pages["⚙️ First-Time Setup"] = self._create_text_page(
            "⚙️ First-Time Setup",
            self._get_first_time_setup_content()
        )
        self.content_stack.addWidget(self.pages["⚙️ First-Time Setup"])

        self.pages["📊 Understanding the Interface"] = self._create_interface_page()
        self.content_stack.addWidget(self.pages["📊 Understanding the Interface"])

        # Configuration Guide Pages
        self.pages["📋 Strategy Tab"] = self._create_strategy_tab_page()
        self.content_stack.addWidget(self.pages["📋 Strategy Tab"])

        self.pages["⏱ Timeframes Tab"] = self._create_timeframes_tab_page()
        self.content_stack.addWidget(self.pages["⏱ Timeframes Tab"])

        self.pages["📊 Instrument Tab"] = self._create_instrument_tab_page()
        self.content_stack.addWidget(self.pages["📊 Instrument Tab"])

        self.pages["🛡 Risk Tab"] = self._create_risk_tab_page()
        self.content_stack.addWidget(self.pages["🛡 Risk Tab"])

        self.pages["💰 Costs Tab"] = self._create_costs_tab_page()
        self.content_stack.addWidget(self.pages["💰 Costs Tab"])

        self.pages["⚙ Execution Tab"] = self._create_execution_tab_page()
        self.content_stack.addWidget(self.pages["⚙ Execution Tab"])

        self.pages["🎯 Complete Walkthrough"] = self._create_walkthrough_page()
        self.content_stack.addWidget(self.pages["🎯 Complete Walkthrough"])

        # Backtest Concepts Pages
        self.pages["📈 Spot Data & Resampling"] = self._create_text_page(
            "📈 Spot Data & Resampling",
            self._get_spot_data_content()
        )
        self.content_stack.addWidget(self.pages["📈 Spot Data & Resampling"])

        self.pages["📊 Option Pricing"] = self._create_option_pricing_page()
        self.content_stack.addWidget(self.pages["📊 Option Pricing"])

        self.pages["⚗️ Synthetic vs Real Data"] = self._create_synthetic_data_page()
        self.content_stack.addWidget(self.pages["⚗️ Synthetic vs Real Data"])

        self.pages["🎯 Entry & Exit Logic"] = self._create_entry_exit_page()
        self.content_stack.addWidget(self.pages["🎯 Entry & Exit Logic"])

        self.pages["⚖️ Position Management"] = self._create_text_page(
            "⚖️ Position Management",
            self._get_position_management_content()
        )
        self.content_stack.addWidget(self.pages["⚖️ Position Management"])

        self.pages["⏱️ Multi-Timeframe Analysis"] = self._create_multi_tf_page()
        self.content_stack.addWidget(self.pages["⏱️ Multi-Timeframe Analysis"])

        self.pages["📉 Equity Curves"] = self._create_equity_curve_tab_page()
        self.content_stack.addWidget(self.pages["📉 Equity Curves"])

        # Results Interpretation Pages
        self.pages["📈 Overview Tab"] = self._create_overview_tab_page()
        self.content_stack.addWidget(self.pages["📈 Overview Tab"])

        self.pages["📋 Trade Log Tab"] = self._create_trade_log_page()
        self.content_stack.addWidget(self.pages["📋 Trade Log Tab"])

        self.pages["🔬 Strategy Analysis Tab"] = self._create_strategy_analysis_page()
        self.content_stack.addWidget(self.pages["🔬 Strategy Analysis Tab"])

        self.pages["📉 Equity Curve Tab"] = self._create_equity_curve_tab_page()
        self.content_stack.addWidget(self.pages["📉 Equity Curve Tab"])

        self.pages["🔍 Candle Debug Tab"] = self._create_candle_debug_page()
        self.content_stack.addWidget(self.pages["🔍 Candle Debug Tab"])

        self.pages["📊 Understanding Metrics"] = self._create_metrics_page()
        self.content_stack.addWidget(self.pages["📊 Understanding Metrics"])

        self.pages["📈 Reading Equity Curves"] = self._create_reading_equity_page()
        self.content_stack.addWidget(self.pages["📈 Reading Equity Curves"])

        # Option Pricing Pages
        self.pages["📈 Black-Scholes Model"] = self._create_black_scholes_page()
        self.content_stack.addWidget(self.pages["📈 Black-Scholes Model"])

        self.pages["🌪️ Volatility Sources"] = self._create_volatility_page()
        self.content_stack.addWidget(self.pages["🌪️ Volatility Sources"])

        self.pages["📊 VIX vs Historical Volatility"] = self._create_vix_vs_hv_page()
        self.content_stack.addWidget(self.pages["📊 VIX vs Historical Volatility"])

        self.pages["📅 Expiry Calculation"] = self._create_expiry_page()
        self.content_stack.addWidget(self.pages["📅 Expiry Calculation"])

        self.pages["⚗️ Synthetic Price Generation"] = self._create_synthetic_generation_page()
        self.content_stack.addWidget(self.pages["⚗️ Synthetic Price Generation"])

        self.pages["✅ Real Data Priority"] = self._create_real_data_page()
        self.content_stack.addWidget(self.pages["✅ Real Data Priority"])

        # Risk Management Pages
        self.pages["🎯 Take Profit (TP)"] = self._create_tp_page()
        self.content_stack.addWidget(self.pages["🎯 Take Profit (TP)"])

        self.pages["🛑 Stop Loss (SL)"] = self._create_sl_page()
        self.content_stack.addWidget(self.pages["🛑 Stop Loss (SL)"])

        self.pages["🏃 Trailing Stop Loss"] = self._create_trailing_sl_page()
        self.content_stack.addWidget(self.pages["🏃 Trailing Stop Loss"])

        self.pages["📉 Index-Based Stop Loss"] = self._create_index_sl_page()
        self.content_stack.addWidget(self.pages["📉 Index-Based Stop Loss"])

        self.pages["⏱️ Max Hold Bars"] = self._create_max_hold_page()
        self.content_stack.addWidget(self.pages["⏱️ Max Hold Bars"])

        self.pages["📊 Risk-Reward Ratios"] = self._create_risk_reward_page()
        self.content_stack.addWidget(self.pages["📊 Risk-Reward Ratios"])

        self.pages["⏸️ Sideway Zone Skip"] = self._create_sideway_zone_page()
        self.content_stack.addWidget(self.pages["⏸️ Sideway Zone Skip"])

        # Costs & Execution Pages
        self.pages["📉 Slippage"] = self._create_slippage_page()
        self.content_stack.addWidget(self.pages["📉 Slippage"])

        self.pages["💸 Brokerage"] = self._create_brokerage_page()
        self.content_stack.addWidget(self.pages["💸 Brokerage"])

        self.pages["📊 Position Sizing"] = self._create_position_sizing_page()
        self.content_stack.addWidget(self.pages["📊 Position Sizing"])

        self.pages["💵 Capital Management"] = self._create_capital_page()
        self.content_stack.addWidget(self.pages["💵 Capital Management"])

        self.pages["⚡ Execution Intervals"] = self._create_execution_interval_page()
        self.content_stack.addWidget(self.pages["⚡ Execution Intervals"])

        # Advanced Features Pages
        self.pages["📤 Export Results"] = self._create_export_page()
        self.content_stack.addWidget(self.pages["📤 Export Results"])

        self.pages["📥 Import Configurations"] = self._create_import_page()
        self.content_stack.addWidget(self.pages["📥 Import Configurations"])

        self.pages["🔄 Batch Testing"] = self._create_batch_testing_page()
        self.content_stack.addWidget(self.pages["🔄 Batch Testing"])

        # Troubleshooting Pages
        self.pages["❌ Common Errors"] = self._create_errors_page()
        self.content_stack.addWidget(self.pages["❌ Common Errors"])

        self.pages["🔍 Debugging Tips"] = self._create_debugging_page()
        self.content_stack.addWidget(self.pages["🔍 Debugging Tips"])

        self.pages["📊 Log Analysis"] = self._create_log_analysis_page()
        self.content_stack.addWidget(self.pages["📊 Log Analysis"])

        self.pages["⚠️ Performance Issues"] = self._create_performance_page()
        self.content_stack.addWidget(self.pages["⚠️ Performance Issues"])

        self.pages["❓ FAQ"] = self._create_faq_page()
        self.content_stack.addWidget(self.pages["❓ FAQ"])

        # Best Practices Pages
        self.pages["🎯 Setting Up Backtests"] = self._create_setup_practices_page()
        self.content_stack.addWidget(self.pages["🎯 Setting Up Backtests"])

        self.pages["📊 Avoiding Overfitting"] = self._create_overfitting_page()
        self.content_stack.addWidget(self.pages["📊 Avoiding Overfitting"])

        self.pages["📈 Interpreting Results"] = self._create_interpreting_results_page()
        self.content_stack.addWidget(self.pages["📈 Interpreting Results"])

        self.pages["⚖️ Risk Management"] = self._create_risk_practices_page()
        self.content_stack.addWidget(self.pages["⚖️ Risk Management"])

        self.pages["🔄 Iterative Improvement"] = self._create_iterative_page()
        self.content_stack.addWidget(self.pages["🔄 Iterative Improvement"])

        self.pages["⚠️ Common Mistakes"] = self._create_mistakes_page()
        self.content_stack.addWidget(self.pages["⚠️ Common Mistakes"])

        # Keyboard Shortcuts
        self.pages["⌨️ Keyboard Shortcuts"] = self._create_shortcuts_page()
        self.content_stack.addWidget(self.pages["⌨️ Keyboard Shortcuts"])

        # Glossary
        self.pages["📚 Glossary"] = self._create_glossary_page()
        self.content_stack.addWidget(self.pages["📚 Glossary"])

    def _create_welcome_page(self) -> QWidget:
        """Create the welcome page with quick actions"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Welcome header
        header = QLabel("🚀 Welcome to the Backtest System!")
        header.setStyleSheet(f"color:{BLUE}; font-size:24pt; font-weight:bold;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Subtitle
        subtitle = QLabel("Your complete toolkit for testing and validating trading strategies")
        subtitle.setStyleSheet(f"color:{DIM}; font-size:14pt;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Quick action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(20)

        quick_start_btn = QPushButton("🚀 Quick Start")
        quick_start_btn.setFixedSize(200, 60)
        quick_start_btn.clicked.connect(lambda: self.show_page("🚀 Quick Start Guide"))
        actions_layout.addWidget(quick_start_btn)

        config_guide_btn = QPushButton("⚙️ Configuration")
        config_guide_btn.setFixedSize(200, 60)
        config_guide_btn.clicked.connect(lambda: self.show_page("⚙️ Execution Tab"))
        actions_layout.addWidget(config_guide_btn)

        results_btn = QPushButton("📊 Understanding Results")
        results_btn.setFixedSize(200, 60)
        results_btn.clicked.connect(lambda: self.show_page("📊 Understanding Metrics"))
        actions_layout.addWidget(results_btn)

        layout.addLayout(actions_layout)

        # Quick stats/info cards
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)

        # Card 1: Key Features
        features_card = QGroupBox("✨ Key Features")
        features_card.setStyleSheet(f"""
            QGroupBox {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }}
            QGroupBox::title {{
                color: {BLUE};
                left: 10px;
            }}
        """)
        features_layout = QVBoxLayout(features_card)
        features_layout.addWidget(QLabel("• Realistic option pricing (Black-Scholes)"))
        features_layout.addWidget(QLabel("• VIX or historical volatility"))
        features_layout.addWidget(QLabel("• Multi-timeframe analysis"))
        features_layout.addWidget(QLabel("• Comprehensive risk management"))
        features_layout.addWidget(QLabel("• Per-candle debugging"))
        stats_layout.addWidget(features_card)

        # Card 2: Getting Started
        start_card = QGroupBox("🚀 Getting Started")
        start_card.setStyleSheet(f"""
            QGroupBox {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }}
            QGroupBox::title {{
                color: {GREEN};
                left: 10px;
            }}
        """)
        start_layout = QVBoxLayout(start_card)
        start_layout.addWidget(QLabel("1. Select a strategy"))
        start_layout.addWidget(QLabel("2. Choose date range"))
        start_layout.addWidget(QLabel("3. Set risk parameters"))
        start_layout.addWidget(QLabel("4. Click ▶ Run Backtest"))
        start_layout.addWidget(QLabel("5. Analyze results"))
        stats_layout.addWidget(start_card)

        layout.addLayout(stats_layout)

        # Getting started guide
        guide = QTextEdit()
        guide.setReadOnly(True)
        guide.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 15px;
                font-size: 11pt;
            }}
        """)
        guide.setHtml(self._get_welcome_guide_content())
        layout.addWidget(guide, 1)

        return widget

    def _get_welcome_guide_content(self) -> str:
        """Get content for the welcome guide"""
        return f"""
        <h2>📋 Getting Started in 3 Steps</h2>
        <table width="100%">
            <tr>
                <td width="33%" align="center" style="padding: 10px;">
                    <h3 style="color: {GREEN};">1️⃣ Configure</h3>
                    <p>Select your strategy, set date range, and configure risk parameters in the right sidebar</p>
                </td>
                <td width="33%" align="center" style="padding: 10px;">
                    <h3 style="color: {GREEN};">2️⃣ Run</h3>
                    <p>Click the green ▶ Run Backtest button and watch the progress</p>
                </td>
                <td width="33%" align="center" style="padding: 10px;">
                    <h3 style="color: {GREEN};">3️⃣ Analyze</h3>
                    <p>Review results across multiple tabs: Overview, Trade Log, Strategy Analysis, and more</p>
                </td>
            </tr>
        </table>

        <h3>💡 Pro Tip</h3>
        <p>Start with a simple strategy and default parameters (TP=30%, SL=25%) to verify everything works. Use the Candle Debug tab to see exactly why signals fire or don't fire.</p>

        <h3>🔍 Quick Links</h3>
        <ul>
            <li><b>Configuration Guide:</b> Learn about all settings in the right sidebar</li>
            <li><b>Understanding Results:</b> How to interpret metrics and charts</li>
            <li><b>Troubleshooting:</b> Fix common issues and errors</li>
            <li><b>FAQ:</b> Answers to frequently asked questions</li>
        </ul>

        <h3>📊 Sample Backtest Workflow</h3>
        <ol>
            <li><b>Select Strategy:</b> Choose a strategy from the dropdown in Strategy tab</li>
            <li><b>Set Date Range:</b> Last 30 days in Instrument tab</li>
            <li><b>Configure Risk:</b> TP=30%, SL=25% in Risk tab</li>
            <li><b>Set Costs:</b> Slippage=0.25%, Brokerage=₹40 in Costs tab</li>
            <li><b>Choose Timeframes:</b> Select 5m (execution) and 15m (analysis)</li>
            <li><b>Run:</b> Click ▶ Run Backtest and wait</li>
            <li><b>Review:</b> Check Overview for summary, Trade Log for details</li>
        </ol>

        <h3>⚠️ Important Notes</h3>
        <ul>
            <li>First 15 bars are warmup - no signals during this period</li>
            <li>Sideway zone (12:00-14:00) skips entries if enabled</li>
            <li>Synthetic prices (⚗) are used when real option data unavailable</li>
            <li>Always include realistic slippage and brokerage in results</li>
        </ul>
        """
    def _create_quick_start_page(self) -> QWidget:
        """Create the quick start guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("🚀 Quick Start Guide")
        title.setStyleSheet(f"color:{BLUE}; font-size:20pt; font-weight:bold;")
        layout.addWidget(title)

        # Steps
        steps_widget = QWidget()
        steps_layout = QVBoxLayout(steps_widget)
        steps_layout.setSpacing(20)

        steps = [
            ("1️⃣ Select Your Strategy",
             "Choose a strategy from the dropdown in the Strategy tab. The active strategy will be used for signal generation."),
            ("2️⃣ Set Date Range",
             "In the Instrument tab, set your start and end dates. Choose a sufficiently long period (30-90 days) for meaningful results."),
            ("3️⃣ Configure Risk Parameters",
             "In the Risk tab, set your Take Profit and Stop Loss percentages. Start with TP=30%, SL=25%."),
            ("4️⃣ Set Costs",
             "In the Costs tab, enter your slippage (0.25%) and brokerage (₹40/lot) values."),
            ("5️⃣ Choose Timeframes",
             "In the Timeframes tab, select which analysis timeframes to evaluate (at least the execution interval)."),
            ("6️⃣ Configure Execution",
             "In the Execution tab, set your execution interval (usually 5 minutes) and volatility source."),
            ("7️⃣ Run Backtest",
             "Click the green ▶ Run Backtest button and wait for completion."),
            ("8️⃣ Analyze Results",
             "Review the Overview tab for summary statistics, Trade Log for individual trades, and Strategy Analysis for signal breakdowns.")
        ]

        for title_text, description in steps:
            step_frame = QFrame()
            step_frame.setStyleSheet(f"""
                QFrame {{
                    background: {BG_ITEM};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                    padding: 15px;
                }}
            """)
            step_layout = QVBoxLayout(step_frame)

            title_label = QLabel(title_text)
            title_label.setStyleSheet(f"color:{GREEN}; font-size:14pt; font-weight:bold;")
            step_layout.addWidget(title_label)

            desc_label = QLabel(description)
            desc_label.setStyleSheet(f"color:{DIM}; font-size:11pt;")
            desc_label.setWordWrap(True)
            step_layout.addWidget(desc_label)

            steps_layout.addWidget(step_frame)

        layout.addWidget(steps_widget)
        layout.addStretch()

        return widget

    def _create_interface_page(self) -> QWidget:
        """Create the interface guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("📊 Understanding the Interface")
        title.setStyleSheet(f"color:{BLUE}; font-size:20pt; font-weight:bold;")
        layout.addWidget(title)

        # Interface sections
        sections = [
            ("📈 Results Panel (Left/Center)",
             "The main area displays backtest results across multiple tabs:\n"
             "• Overview: Summary statistics and key metrics\n"
             "• Trade Log: Detailed list of all trades\n"
             "• Strategy Analysis: Multi-timeframe signal breakdowns\n"
             "• Equity Curve: Visual representation of P&L over time\n"
             "• Candle Debug: Per-candle signal evaluation data"),

            ("⚙️ Settings Sidebar (Right)",
             "Configure your backtest parameters in these tabs:\n"
             "• Strategy: Choose which trading strategy to test\n"
             "• Timeframes: Select analysis timeframes\n"
             "• Instrument: Set derivative, expiry, lot size, date range\n"
             "• Risk: Configure TP/SL and other risk parameters\n"
             "• Costs: Set slippage, brokerage, and capital\n"
             "• Execution: Choose interval and volatility source"),

            ("🎮 Bottom Bar",
             "Controls and progress:\n"
             "• Status label: Current operation and messages\n"
             "• Progress bar: Backtest completion percentage\n"
             "• ▶ Run Backtest: Start a new backtest\n"
             "• ■ Stop: Cancel running backtest")
        ]

        for section_title, section_desc in sections:
            section_frame = QFrame()
            section_frame.setStyleSheet(f"""
                QFrame {{
                    background: {BG_ITEM};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                    margin-top: 10px;
                }}
            """)
            section_layout = QVBoxLayout(section_frame)

            title_label = QLabel(section_title)
            title_label.setStyleSheet(f"color:{GREEN}; font-size:13pt; font-weight:bold;")
            section_layout.addWidget(title_label)

            desc_label = QLabel(section_desc)
            desc_label.setStyleSheet(f"color:{DIM}; font-size:11pt;")
            desc_label.setWordWrap(True)
            section_layout.addWidget(desc_label)

            layout.addWidget(section_frame)

        layout.addStretch()
        return widget

    def _create_strategy_tab_page(self) -> QWidget:
        """Create the strategy tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>📋 Strategy Tab</h1>

        <p>The Strategy tab allows you to select which trading strategy to test.</p>

        <h2 style='color:{GREEN}'>Components</h2>

        <h3>📋 Active Strategy Dropdown</h3>
        <ul>
            <li><b>Function:</b> Select which strategy to use for signal generation</li>
            <li><b>Options:</b> All strategies saved in the database</li>
            <li><b>Note:</b> The active strategy from live trading is marked with ⚡</li>
        </ul>

        <h3>🔄 Refresh List Button</h3>
        <ul>
            <li><b>Function:</b> Reload strategies from database</li>
            <li><b>Use when:</b> You've added/edited strategies in the Strategy Editor</li>
        </ul>

        <h3>📊 Strategy Stats</h3>
        <ul>
            <li><b>Rules:</b> Total number of rules across all signal groups</li>
            <li><b>Min Confidence:</b> Minimum confidence threshold for signals</li>
            <li><b>Enabled Groups:</b> How many of the 5 signal groups are active</li>
        </ul>

        <h2 style='color:{GREEN}'>Tips</h2>
        <ul>
            <li>Always test with the same strategy you plan to use live</li>
            <li>Check the stats to ensure the strategy has enough rules</li>
            <li>Use the Strategy Editor to modify and create new strategies</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_timeframes_tab_page(self) -> QWidget:
        """Create the timeframes tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>⏱ Timeframes Tab</h1>

        <p>Select which timeframes to analyse during the backtest. The analysis runs after the main backtest and provides multi-timeframe signal breakdowns.</p>

        <h2 style='color:{GREEN}'>Available Timeframes</h2>

        <h3>Short Term (1-5m)</h3>
        <ul>
            <li><b>1m, 2m, 3m, 5m:</b> For scalping and very short-term strategies</li>
            <li><b>Use when:</b> Trading intraday momentum, quick entries/exits</li>
        </ul>

        <h3>Medium Term (10-30m)</h3>
        <ul>
            <li><b>10m, 15m, 30m:</b> Most common for day trading</li>
            <li><b>Use when:</b> Standard day trading, catching medium moves</li>
        </ul>

        <h3>Long Term (60-240m)</h3>
        <ul>
            <li><b>60m, 120m, 240m:</b> For swing trading and trend following</li>
            <li><b>Use when:</b> Holding positions for hours to days</li>
        </ul>

        <h2 style='color:{GREEN}'>Important Notes</h2>
        <ul>
            <li>The execution interval (set in Execution tab) is ALWAYS included in analysis</li>
            <li>Selecting too many timeframes increases analysis time</li>
            <li>Timeframes are generated by resampling 1-minute spot data</li>
            <li>Analysis runs independently of main backtest</li>
        </ul>

        <h2 style='color:{GREEN}'>Best Practices</h2>
        <ul>
            <li>Start with 2-3 timeframes (e.g., 5m, 15m, 60m)</li>
            <li>Include the execution interval to see exact signals</li>
            <li>Add higher timeframes to check trend context</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_instrument_tab_page(self) -> QWidget:
        """Create the instrument tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{ORANGE}'>📊 Instrument Tab</h1>

        <p>Configure the underlying instrument and backtest date range.</p>

        <h2 style='color:{GREEN}'>Instrument Settings</h2>

        <h3>Derivative</h3>
        <ul>
            <li><b>Options:</b> NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX</li>
            <li><b>Strike steps:</b> 50, 100, 50, 25, 100 respectively</li>
            <li><b>Impact:</b> Determines which options are priced</li>
        </ul>

        <h3>Expiry Type</h3>
        <ul>
            <li><b>Weekly:</b> Next weekly expiry (default for most indices)</li>
            <li><b>Monthly:</b> End-of-month expiry (for monthly options)</li>
        </ul>

        <h3>Lot Size</h3>
        <ul>
            <li><b>NIFTY:</b> 50</li>
            <li><b>BANKNIFTY:</b> 25</li>
            <li><b>FINNIFTY:</b> 40</li>
            <li><b>MIDCPNIFTY:</b> 75</li>
            <li><b>SENSEX:</b> 10</li>
        </ul>

        <h3>Number of Lots</h3>
        <ul>
            <li>Position size multiplier</li>
            <li>Example: 2 lots × 50 lot size = 100 contracts</li>
        </ul>

        <h2 style='color:{GREEN}'>Date Range</h2>

        <h3>From / To</h3>
        <ul>
            <li>Select start and end dates for the backtest</li>
            <li><b>Recommendation:</b> Minimum 30 days for meaningful results</li>
            <li><b>Caution:</b> Very long ranges (>1 year) may take time to process</li>
        </ul>

        <h2 style='color:{GREEN}'>Tips</h2>
        <ul>
            <li>Match lot size to the actual derivative</li>
            <li>Use weekly expiry for most strategies (higher volume)</li>
            <li>Include both trending and range-bound periods for robust testing</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_risk_tab_page(self) -> QWidget:
        """Create the risk tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{WARN}'>🛡 Risk Tab</h1>

        <p>Configure risk management parameters for the backtest.</p>

        <h2 style='color:{GREEN}'>Take Profit / Stop Loss</h2>

        <h3>Take Profit (TP)</h3>
        <ul>
            <li><b>Purpose:</b> Lock in profits when option price rises by X%</li>
            <li><b>Range:</b> 0-500% (recommended: 20-50%)</li>
            <li><b>Execution:</b> Triggers when option HIGH reaches TP level</li>
        </ul>

        <h3>Stop Loss (SL)</h3>
        <ul>
            <li><b>Purpose:</b> Limit losses when option price falls by X%</li>
            <li><b>Range:</b> 0-100% (recommended: 15-30%)</li>
            <li><b>Execution:</b> Triggers when option LOW reaches SL level</li>
        </ul>

        <h2 style='color:{GREEN}'>Risk Options</h2>

        <h3>Skip Sideway Zone (12:00-14:00)</h3>
        <ul>
            <li><b>Purpose:</b> Avoid low-volatility afternoon period</li>
            <li><b>Effect:</b> No entries during this time, existing positions unaffected</li>
            <li><b>Recommendation:</b> Keep enabled for index options</li>
        </ul>

        <h2 style='color:{GREEN}'>Advanced Risk Parameters</h2>
        <p><i>These can be configured in BacktestConfig but not directly in UI:</i></p>
        <ul>
            <li><b>Index SL:</b> Stop based on spot price movement (e.g., 100 points)</li>
            <li><b>Trailing SL:</b> Moves up with profits (as % of entry)</li>
            <li><b>Max Hold Bars:</b> Force exit after N bars regardless of signal</li>
        </ul>

        <h2 style='color:{GREEN}'>Risk-Reward Considerations</h2>
        <ul>
            <li><b>Conservative:</b> TP=20%, SL=10% (RR=2:1)</li>
            <li><b>Moderate:</b> TP=30%, SL=20% (RR=1.5:1)</li>
            <li><b>Aggressive:</b> TP=50%, SL=30% (RR≈1.7:1)</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_costs_tab_page(self) -> QWidget:
        """Create the costs tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:#f97583'>💰 Costs Tab</h1>

        <p>Configure trading costs and capital.</p>

        <h2 style='color:{GREEN}'>Execution Costs</h2>

        <h3>Slippage (%)</h3>
        <ul>
            <li><b>Purpose:</b> Simulate market impact and order execution delay</li>
            <li><b>Typical range:</b> 0.1-0.5%</li>
            <li><b>Default:</b> 0.25%</li>
            <li><b>How it works:</b> Entry price = option_price × (1 + slippage%)</li>
            <li style='margin-left:20px'>Exit price = option_price × (1 - slippage%)</li>
        </ul>

        <h3>Brokerage per Lot (₹)</h3>
        <ul>
            <li><b>Purpose:</b> Fixed cost per lot round-trip (entry + exit)</li>
            <li><b>Typical:</b> ₹20-50 per lot</li>
            <li><b>Default:</b> ₹40</li>
            <li><b>Calculation:</b> Brokerage × lots × 2 (entry + exit)</li>
        </ul>

        <h2 style='color:{GREEN}'>Capital</h2>

        <h3>Initial Capital (₹)</h3>
        <ul>
            <li><b>Purpose:</b> Starting capital for the backtest</li>
            <li><b>Range:</b> ₹10,000 - ₹10,00,00,000</li>
            <li><b>Effect:</b> Used for position sizing and drawdown calculations</li>
        </ul>

        <h2 style='color:{GREEN}'>Impact on Results</h2>
        <ul>
            <li>Higher slippage = more conservative (worse) results</li>
            <li>Higher brokerage = fewer small profits, more losing trades</li>
            <li>Always use realistic costs for your broker</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_execution_tab_page(self) -> QWidget:
        """Create the execution tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{ACCENT}'>⚙ Execution Tab</h1>

        <p>Configure execution parameters and volatility sources.</p>

        <h2 style='color:{GREEN}'>Execution Options</h2>

        <h3>Execution Interval (minutes)</h3>
        <ul>
            <li><b>Purpose:</b> Candle width for signal evaluation and trade execution</li>
            <li><b>Options:</b> 1, 2, 3, 5, 10, 15, 30 minutes</li>
            <li><b>Default:</b> 5 minutes</li>
            <li><b>Note:</b> Spot data is always fetched at 1-min and resampled</li>
        </ul>

        <h3>Auto-export Analysis</h3>
        <ul>
            <li><b>Purpose:</b> Automatically save analysis data after backtest</li>
            <li><b>Effect:</b> Saves CSV files for each timeframe in chosen directory</li>
        </ul>

        <h2 style='color:{GREEN}'>Volatility Source</h2>

        <h3>Use India VIX</h3>
        <ul>
            <li><b>When checked:</b> Fetches India VIX data from NSE/yfinance</li>
            <li><b>Pros:</b> More realistic, reflects market volatility</li>
            <li><b>Cons:</b> Requires internet, slower startup</li>
        </ul>

        <h3>Use Historical Volatility (unchecked)</h3>
        <ul>
            <li><b>When unchecked:</b> Computes rolling HV from spot candles</li>
            <li><b>Pros:</b> No network calls, fully offline, faster</li>
            <li><b>Cons:</b> Less realistic, may not match actual option IV</li>
        </ul>

        <h2 style='color:{GREEN}'>Important Notes</h2>
        <ul>
            <li>Execution interval determines trading frequency</li>
            <li>Shorter intervals = more signals, more noise</li>
            <li>Longer intervals = fewer signals, cleaner trends</li>
            <li>HV mode uses last 20 closes for rolling volatility</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_walkthrough_page(self) -> QWidget:
        """Create the complete walkthrough page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("🎯 Complete Walkthrough: Testing a Strategy")
        title.setStyleSheet(f"color:{BLUE}; font-size:20pt; font-weight:bold;")
        layout.addWidget(title)

        # Walkthrough steps
        steps = [
            ("Step 1: Strategy Selection",
             "1. Open Strategy Editor (from main TradingGUI)\n"
             "2. Create a new strategy or select an existing one\n"
             "3. Verify the strategy has rules and is enabled\n"
             "4. Note the min confidence threshold (default 60%)"),

            ("Step 2: Backtest Configuration",
             "1. In Strategy tab, select your strategy\n"
             "2. In Timeframes tab, select '5m' (execution) and '15m' (trend)\n"
             "3. In Instrument tab:\n"
             "   • Derivative: NIFTY\n"
             "   • Expiry: weekly\n"
             "   • Lot Size: 50, Lots: 1\n"
             "   • Date: Last 30 days"),

            ("Step 3: Risk Setup",
             "1. In Risk tab, enable TP and SL\n"
             "2. Set TP: 30%, SL: 25%\n"
             "3. Enable 'Skip Sideway Zone'"),

            ("Step 4: Costs",
             "1. Slippage: 0.25%\n"
             "2. Brokerage: ₹40\n"
             "3. Capital: ₹100,000"),

            ("Step 5: Execution",
             "1. Execution interval: 5m\n"
             "2. Volatility: Use India VIX (if online) or HV (offline)"),

            ("Step 6: Run and Analyze",
             "1. Click ▶ Run Backtest\n"
             "2. Wait for completion (watch progress bar)\n"
             "3. Review results in each tab:\n"
             "   • Overview: Key metrics\n"
             "   • Trade Log: Individual trades\n"
             "   • Strategy Analysis: Signal breakdowns\n"
             "   • Equity Curve: P&L visualization\n"
             "   • Candle Debug: Per-candle details"),

            ("Step 7: Iterate",
             "1. Adjust parameters based on results\n"
             "2. Test different timeframes\n"
             "3. Modify strategy rules if needed\n"
             "4. Re-run and compare")
        ]

        for step_title, step_desc in steps:
            step_frame = QFrame()
            step_frame.setStyleSheet(f"""
                QFrame {{
                    background: {BG_ITEM};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                    margin-top: 10px;
                    padding: 15px;
                }}
            """)
            step_layout = QVBoxLayout(step_frame)

            title_label = QLabel(step_title)
            title_label.setStyleSheet(f"color:{GREEN}; font-size:13pt; font-weight:bold;")
            step_layout.addWidget(title_label)

            desc_label = QLabel(step_desc)
            desc_label.setStyleSheet(f"color:{DIM}; font-size:11pt;")
            desc_label.setWordWrap(True)
            step_layout.addWidget(desc_label)

            layout.addWidget(step_frame)

        layout.addStretch()
        return widget

    def _create_option_pricing_page(self) -> QWidget:
        """Create the option pricing guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{INFO}'>📊 Option Pricing in Backtests</h1>

        <p>The backtest engine uses a sophisticated approach to price options when historical data is unavailable.</p>

        <h2 style='color:{GREEN}'>Priority Chain</h2>
        <ol>
            <li><b>Real broker historical data</b> - If available and valid</li>
            <li><b>Black-Scholes synthetic price</b> - Fallback using theoretical model</li>
        </ol>

        <h2 style='color:{GREEN}'>Black-Scholes Model</h2>
        <p>The Black-Scholes formula for European options:</p>
        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace;'>
            C = S·N(d₁) - K·e⁻ʳᵀ·N(d₂)<br>
            P = K·e⁻ʳᵀ·N(-d₂) - S·N(-d₁)<br>
            where:<br>
            d₁ = [ln(S/K) + (r + σ²/2)T] / (σ√T)<br>
            d₂ = d₁ - σ√T
        </div>

        <h2 style='color:{GREEN}'>Input Parameters</h2>
        <ul>
            <li><b>S (Spot):</b> Current underlying price</li>
            <li><b>K (Strike):</b> ATM strike (rounded to derivative step)</li>
            <li><b>T (Time):</b> Time to expiry in years</li>
            <li><b>r (Risk-free rate):</b> 6.5% (India 91-day T-bill)</li>
            <li><b>σ (Volatility):</b> From VIX or historical HV</li>
            <li><b>q (Dividend):</b> 0 (indices)</li>
        </ul>

        <h2 style='color:{GREEN}'>OHLC Generation</h2>
        <p>For synthetic bars, the engine generates OHLC prices:</p>
        <ul>
            <li><b>Open:</b> Price at bar start (using T + bar fraction)</li>
            <li><b>Close:</b> Price at bar end</li>
            <li><b>High:</b> Max price using max spot high/low based on option type</li>
            <li><b>Low:</b> Min price using min spot high/low based on option type</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_synthetic_data_page(self) -> QWidget:
        """Create the synthetic vs real data guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{WARN}'>⚗️ Synthetic vs Real Data</h1>

        <h2 style='color:{GREEN}'>Why Synthetic Data?</h2>
        <p>Historical option data is often unavailable for expired strikes. The backtest engine uses Black-Scholes to generate realistic option prices when real data is missing.</p>

        <h2 style='color:{GREEN}'>Visual Indicators</h2>

        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Element</th>
                <th>Real Data</th>
                <th>Synthetic Data</th>
            </tr>
            <tr>
                <td><b>Trade Log Badge</b></td>
                <td style='color:{GREEN};'>✓ (green)</td>
                <td style='color:{WARN};'>⚗ (amber)</td>
            </tr>
            <tr>
                <td><b>Trade Row Background</b></td>
                <td>Normal</td>
                <td style='background:{SYNTH_BG};'>Amber-tinted</td>
            </tr>
            <tr>
                <td><b>Equity Curve Highlight</b></td>
                <td>Normal line</td>
                <td>Amber shaded regions</td>
            </tr>
            <tr>
                <td><b>Data Quality Metric</b></td>
                <td>% real bars</td>
                <td>Shows R/S count</td>
            </tr>
        </table>

        <h2 style='color:{GREEN}'>Reliability Considerations</h2>
        <ul>
            <li><b>High reliability (80%+ real):</b> Results very trustworthy</li>
            <li><b>Medium reliability (40-80% real):</b> Reasonable confidence</li>
            <li><b>Low reliability (<40% real):</b> Results largely theoretical</li>
        </ul>

        <h2 style='color:{GREEN}'>When Synthetic Data is Used</h2>
        <ul>
            <li>Expired strikes (no longer traded)</li>
            <li>Very deep ITM/OTM strikes</li>
            <li>Weekend/holiday price estimation</li>
            <li>Broker data gaps</li>
        </ul>

        <h2 style='color:{GREEN}'>Accuracy of Synthetic Prices</h2>
        <p>Black-Scholes prices are theoretical and may differ from actual market prices due to:</p>
        <ul>
            <li>Supply/demand imbalances</li>
            <li>Volatility smile/skew</li>
            <li>Bid-ask spreads</li>
            <li>Market maker inventory effects</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_entry_exit_page(self) -> QWidget:
        """Create the entry and exit logic guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>🎯 Entry & Exit Logic</h1>

        <h2 style='color:{GREEN}'>Entry Logic</h2>

        <h3>When FLAT (no position)</h3>
        <ul>
            <li><b>BUY_CALL</b> → Enter CALL position</li>
            <li><b>BUY_PUT</b> → Enter PUT position</li>
            <li>All other signals → WAIT</li>
        </ul>

        <h3>Entry Price</h3>
        <ul>
            <li>Option close price at bar end</li>
            <li>Plus slippage: entry_price = option_close × (1 + slippage%)</li>
        </ul>

        <h2 style='color:{GREEN}'>Exit Logic (Priority Order)</h2>

        <h3>1. Take Profit (TP)</h3>
        <ul>
            <li>Triggers when option HIGH reaches entry_price × (1 + tp%)</li>
            <li>Exit at TP price (minus slippage)</li>
        </ul>

        <h3>2. Stop Loss (SL)</h3>
        <ul>
            <li>Triggers when option LOW reaches entry_price × (1 - sl%)</li>
            <li>Exit at SL price (minus slippage)</li>
        </ul>

        <h3>3. Trailing Stop Loss</h3>
        <ul>
            <li>Tracks highest option price since entry</li>
            <li>Triggers when LOW falls below peak × (1 - trailing_sl%)</li>
        </ul>

        <h3>4. Index Stop Loss</h3>
        <ul>
            <li>CALL: Triggers when spot LOW ≤ entry_spot - index_sl</li>
            <li>PUT: Triggers when spot HIGH ≥ entry_spot + index_sl</li>
        </ul>

        <h3>5. Max Hold Bars</h3>
        <ul>
            <li>Forces exit after N bars regardless of price</li>
            <li>Exit at option close price (minus slippage)</li>
        </ul>

        <h3>6. Signal Exit</h3>
        <ul>
            <li>CALL: EXIT_CALL or BUY_PUT signal</li>
            <li>PUT: EXIT_PUT or BUY_CALL signal</li>
            <li>Exit at option close price (minus slippage)</li>
        </ul>

        <h3>7. Market Close</h3>
        <ul>
            <li>Auto-exit 5 minutes before market close (15:25)</li>
            <li>Prevents overnight exposure (not supported in backtest)</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_multi_tf_page(self) -> QWidget:
        """Create the multi-timeframe analysis guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>⏱️ Multi-Timeframe Analysis</h1>

        <p>The Strategy Analysis tab provides signal breakdowns across multiple timeframes, helping you understand how your strategy performs at different resolutions.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>
        <ol>
            <li>After the main backtest completes, the engine re-runs signal evaluation on each selected timeframe</li>
            <li>Spot data is resampled from 1-minute to the target interval</li>
            <li>Signal results are stored as BarAnalysis objects</li>
        </ol>

        <h2 style='color:{GREEN}'>Analysis Tab Features</h2>

        <h3>Timeframe Selection</h3>
        <ul>
            <li>Choose which timeframe to view</li>
            <li>Results for each timeframe are stored separately</li>
        </ul>

        <h3>Export Options</h3>
        <ul>
            <li><b>Export Timeframe:</b> Save current timeframe as CSV</li>
            <li><b>Export All:</b> Save all selected timeframes</li>
        </ul>

        <h3>Signal Tree</h3>
        <ul>
            <li>Shows each bar's timestamp, spot price, signal, and confidence</li>
            <li>Color-coded by signal type</li>
            <li>Click any bar to see detailed analysis</li>
        </ul>

        <h3>Details Panel</h3>
        <ul>
            <li><b>Confidence scores:</b> Per-group confidence values</li>
            <li><b>Rule evaluations:</b> Which rules passed/failed</li>
            <li><b>Indicator values:</b> Current and previous values</li>
        </ul>

        <h2 style='color:{GREEN}'>Use Cases</h2>
        <ul>
            <li><b>Trend confirmation:</b> Check higher timeframe trend alignment</li>
            <li><b>Signal quality:</b> Strong signals should appear across timeframes</li>
            <li><b>Optimization:</b> Find the best timeframe for your strategy</li>
            <li><b>Debugging:</b> Understand why signals fired/didn't fire</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_overview_tab_page(self) -> QWidget:
        """Create the overview tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📈 Overview Tab</h1>

        <p>The Overview tab provides a summary of backtest results with key metrics.</p>

        <h2 style='color:{GREEN}'>Stat Cards</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Metric</th>
                <th>Description</th>
                <th>Good Range</th>
            </tr>
            <tr>
                <td><b>Net P&L</b></td>
                <td>Total profit/loss after all costs</td>
                <td>Positive, ideally >10% of capital</td>
            </tr>
            <tr>
                <td><b>Total Trades</b></td>
                <td>Number of completed trades</td>
                <td>20+ for statistical significance</td>
            </tr>
            <tr>
                <td><b>Win Rate</b></td>
                <td>% of trades that were profitable</td>
                <td>40-60% (higher isn't always better)</td>
            </tr>
            <tr>
                <td><b>Profit Factor</b></td>
                <td>Gross profit / gross loss</td>
                <td>>1.5 (good), >2.0 (excellent)</td>
            </tr>
            <tr>
                <td><b>Best Trade</b></td>
                <td>Highest net profit single trade</td>
                <td>Context-dependent</td>
            </tr>
            <tr>
                <td><b>Worst Trade</b></td>
                <td>Lowest net profit (largest loss)</td>
                <td>Should be less than risk parameters</td>
            </tr>
            <tr>
                <td><b>Avg Net P&L</b></td>
                <td>Average profit per trade</td>
                <td>Positive, covers costs</td>
            </tr>
            <tr>
                <td><b>Max Drawdown</b></td>
                <td>Largest peak-to-trough decline</td>
                <td><20% of capital</td>
            </tr>
            <tr>
                <td><b>Sharpe Ratio</b></td>
                <td>Risk-adjusted return</td>
                <td>>1.0 (good), >2.0 (excellent)</td>
            </tr>
            <tr>
                <td><b>Winners/Losers</b></td>
                <td>Count of profitable/unprofitable trades</td>
                <td>Depends on strategy</td>
            </tr>
            <tr>
                <td><b>Data Quality</b></td>
                <td>% of trades with real option data</td>
                <td>>80% (reliable), 40-80% (moderate)</td>
            </tr>
        </table>

        <h2 style='color:{GREEN}'>Configuration Summary</h2>
        <p>Shows key parameters used in the backtest for quick reference.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_trade_log_page(self) -> QWidget:
        """Create the trade log guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📋 Trade Log Tab</h1>

        <p>The Trade Log shows every completed trade with full details.</p>

        <h2 style='color:{GREEN}'>Column Guide</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Column</th>
                <th>Description</th>
            </tr>
            <tr><td><b>#</b></td><td>Trade sequence number</td></tr>
            <tr><td><b>Dir</b></td><td>Direction: 📈 CE (CALL) or 📉 PE (PUT)</td></tr>
            <tr><td><b>Entry Time</b></td><td>Timestamp of entry bar</td></tr>
            <tr><td><b>Exit Time</b></td><td>Timestamp of exit bar</td></tr>
            <tr><td><b>Spot In</b></td><td>Spot price at entry</td></tr>
            <tr><td><b>Spot Out</b></td><td>Spot price at exit</td></tr>
            <tr><td><b>Strike</b></td><td>Option strike price</td></tr>
            <tr><td><b>Opt Entry</b></td><td>Option price at entry (after slippage)</td></tr>
            <tr><td><b>Opt Exit</b></td><td>Option price at exit (after slippage)</td></tr>
            <tr><td><b>Lots</b></td><td>Number of lots traded</td></tr>
            <tr><td><b>Gross P&L</b></td><td>Profit before costs</td></tr>
            <tr><td><b>Net P&L</b></td><td>Profit after slippage and brokerage</td></tr>
            <tr><td><b>Exit</b></td><td>Exit reason (TP/SL/SIGNAL/MARKET_CLOSE)</td></tr>
            <tr><td><b>Signal</b></td><td>Signal that triggered entry</td></tr>
            <tr><td><b>Src</b></td><td>⚗ = synthetic, ✓ = real data</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Exit Reasons</h2>
        <ul>
            <li><b>TP:</b> Take Profit hit</li>
            <li><b>SL:</b> Stop Loss hit</li>
            <li><b>TRAILING_SL:</b> Trailing Stop Loss hit</li>
            <li><b>INDEX_SL:</b> Index-based Stop Loss hit</li>
            <li><b>MAX_HOLD:</b> Maximum hold bars exceeded</li>
            <li><b>SIGNAL:</b> Exit signal received</li>
            <li><b>MARKET_CLOSE:</b> Forced exit at market close</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_strategy_analysis_page(self) -> QWidget:
        """Create the strategy analysis tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{INFO}'>🔬 Strategy Analysis Tab</h1>

        <p>The Strategy Analysis tab provides detailed per-bar signal breakdowns across multiple timeframes.</p>

        <h2 style='color:{GREEN}'>Features</h2>

        <h3>Toolbar</h3>
        <ul>
            <li><b>Timeframe dropdown:</b> Switch between analysis timeframes</li>
            <li><b>Export buttons:</b> Save analysis data as CSV</li>
            <li><b>Stats label:</b> Shows total bars analysed</li>
        </ul>

        <h3>Signal Tree</h3>
        <ul>
            <li><b>Time:</b> Bar timestamp</li>
            <li><b>Spot:</b> Close price at bar end</li>
            <li><b>Signal:</b> Resolved signal for this bar (color-coded)</li>
            <li><b>Confidence:</b> Overall confidence score</li>
            <li><b>Per-group confidence:</b> Individual group confidence (color-coded: green≥60%, yellow≥30%, grey<30%)</li>
        </ul>

        <h3>Details Panel</h3>
        <p>When you click a bar, you see:</p>
        <ul>
            <li><b>Confidence scores:</b> All 5 signal groups with high/med/low tags</li>
            <li><b>Rule evaluations:</b> Which rules passed/failed (first 3 shown)</li>
            <li><b>Indicator values:</b> Current and previous values with deltas</li>
        </ul>

        <h2 style='color:{GREEN}'>Interpretation Guide</h2>
        <ul>
            <li><b>High confidence (≥60%):</b> Strong signal, multiple rules firing</li>
            <li><b>Medium confidence (30-60%):</b> Moderate signal, some confirmation</li>
            <li><b>Low confidence (<30%):</b> Weak signal, few rules firing</li>
            <li><b>Multiple timeframe agreement:</b> Stronger overall signal</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_equity_curve_tab_page(self) -> QWidget:
        """Create the equity curve tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📉 Equity Curve Tab</h1>

        <p>The Equity Curve tab visualizes your P&L over time.</p>

        <h2 style='color:{GREEN}'>Features</h2>

        <h3>Chart Elements</h3>
        <ul>
            <li><b>Blue line:</b> Equity curve (green if final > initial, red if final < initial)</li>
            <li><b>Shaded fill:</b> Area under the curve</li>
            <li><b>Amber shaded regions:</b> Periods with synthetic option pricing</li>
            <li><b>Triangle markers:</b> Individual trade entries</li>
            <li><b>Green triangles:</b> Winning trades</li>
            <li><b>Red triangles:</b> Losing trades</li>
        </ul>

        <h2 style='color:{GREEN}'>What to Look For</h2>

        <h3>Healthy Curve</h3>
        <ul>
            <li>Steady upward slope</li>
            <li>Minor pullbacks (drawdowns <20%)</li>
            <li>Consistent performance</li>
        </ul>

        <h3>Warning Signs</h3>
        <ul>
            <li>Large drawdowns >20%</li>
            <li>Long flat periods (no trades)</li>
            <li>Erratic spikes/drops</li>
            <li>Performance concentrated in few trades</li>
        </ul>

        <h3>Synthetic Data Impact</h3>
        <p>Amber-shaded regions indicate periods where synthetic pricing was used. If most of your equity curve is amber, results are largely theoretical and should be treated with caution.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_candle_debug_page(self) -> QWidget:
        """Create the candle debug tab guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{INFO}'>🔍 Candle Debug Tab</h1>

        <p>The Candle Debug tab provides per-candle signal evaluation data, invaluable for understanding why signals fired or didn't fire.</p>

        <h2 style='color:{GREEN}'>Features</h2>

        <h3>Toolbar</h3>
        <ul>
            <li><b>Search:</b> Filter by time, signal, indicator values, etc.</li>
            <li><b>Signal filter:</b> Show only specific signals</li>
            <li><b>Action filter:</b> Filter by actual action taken</li>
            <li><b>Skip filter:</b> Show/hide skipped candles</li>
            <li><b>Position filter:</b> Filter by position state</li>
        </ul>

        <h3>Table Columns</h3>
        <ul>
            <li><b>#:</b> Bar index</li>
            <li><b>Time:</b> Candle timestamp</li>
            <li><b>Signal:</b> Raw signal from engine</li>
            <li><b>Conf%:</b> Best confidence among fired groups</li>
            <li><b>Action:</b> What the engine actually did</li>
            <li><b>Pos:</b> Current position (CALL/PUT/FLAT)</li>
            <li><b>Spot Close:</b> Closing price</li>
            <li><b>Skip:</b> Skip reason if candle was skipped</li>
            <li><b>🔍 Detail:</b> Click to open detailed popup</li>
        </ul>

        <h2 style='color:{GREEN}'>Detail Popup</h2>
        <p>Double-click any row or click 🔍 Detail to see comprehensive information:</p>

        <h3>Overview Tab</h3>
        <ul>
            <li><b>Explanation:</b> Human-readable signal explanation</li>
            <li><b>Backtest Override:</b> Any override applied</li>
            <li><b>Spot OHLC:</b> Current candle OHLC</li>
            <li><b>Option OHLC:</b> Option price OHLC (if in position)</li>
        </ul>

        <h3>Signals Tab</h3>
        <ul>
            <li>Each signal group with confidence, threshold, fired status</li>
            <li>Visual confidence bar</li>
            <li>Every rule with pass/fail, detail, and weight</li>
        </ul>

        <h3>Indicators Tab</h3>
        <ul>
            <li>All indicator values with current, previous, and delta</li>
        </ul>

        <h3>Position & TP/SL Tab</h3>
        <ul>
            <li>Position details (entry time/price, strike, bars in trade)</li>
            <li>TP/SL levels and hit status</li>
        </ul>

        <h3>Raw JSON Tab</h3>
        <ul>
            <li>Complete raw debug data for export/analysis</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_metrics_page(self) -> QWidget:
        """Create the metrics explanation page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📊 Understanding Metrics</h1>

        <h2 style='color:{GREEN}'>Core Performance Metrics</h2>

        <h3>Net P&L</h3>
        <p><b>Formula:</b> Σ(exit_price - entry_price) × lots × lot_size - slippage - brokerage</p>
        <p><b>Interpretation:</b> Total profit/loss after all costs. Should be positive and substantial relative to capital.</p>

        <h3>Win Rate</h3>
        <p><b>Formula:</b> (Winning trades / Total trades) × 100</p>
        <p><b>Interpretation:</b> Percentage of profitable trades. 40-60% is typical. Very high win rates (>70%) often indicate small profits with occasional large losses.</p>

        <h3>Profit Factor</h3>
        <p><b>Formula:</b> Gross profit / |Gross loss|</p>
        <p><b>Interpretation:</b> How many rupees gained for every rupee lost. >1.5 is good, >2.0 is excellent. <1.0 means strategy loses money overall.</p>

        <h3>Max Drawdown</h3>
        <p><b>Formula:</b> Maximum peak-to-trough decline in equity curve</p>
        <p><b>Interpretation:</b> Worst-case scenario loss from peak. Should be less than your risk tolerance (typically <20%).</p>

        <h3>Sharpe Ratio</h3>
        <p><b>Formula:</b> (Mean return / Standard deviation of returns) × √252</p>
        <p><b>Interpretation:</b> Risk-adjusted return. >1.0 good, >2.0 excellent. Negative means strategy loses money.</p>

        <h2 style='color:{GREEN}'>Trade Statistics</h2>

        <h3>Average Net P&L</h3>
        <p><b>Formula:</b> Net P&L / Total trades</p>
        <p><b>Interpretation:</b> Average profit per trade. Should exceed average costs (slippage + brokerage).</p>

        <h3>Best/Worst Trade</h3>
        <p><b>Interpretation:</b> Extremes of performance. Large outliers may indicate data errors or need for position sizing limits.</p>

        <h2 style='color:{GREEN}'>Data Quality Metrics</h2>

        <h3>Real Bars / Synthetic Bars</h3>
        <p><b>Interpretation:</b> Count of trades using real vs synthetic option data. More real data = more reliable results.</p>

        <h3>Data Quality %</h3>
        <p><b>Formula:</b> (Real bars / Total bars) × 100</p>
        <p><b>Interpretation:</b> <40% = low confidence, 40-80% = moderate, >80% = high confidence</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_reading_equity_page(self) -> QWidget:
        """Create the equity curve reading guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📈 Reading Equity Curves</h1>

        <h2 style='color:{GREEN}'>Ideal Equity Curve Characteristics</h2>

        <div style='background:{BG_ITEM}; padding:15px; border-radius:8px; margin:15px 0;'>
            <h3 style='color:{GREEN};'>✅ Good Curve</h3>
            <ul>
                <li>Steady, consistent upward slope</li>
                <li>Minor pullbacks (drawdowns <15-20%)</li>
                <li>Increasing slope over time (compounding)</li>
                <li>Regular trade activity</li>
            </ul>
        </div>

        <div style='background:{BG_ITEM}; padding:15px; border-radius:8px; margin:15px 0;'>
            <h3 style='color:{RED};'>⚠️ Warning Signs</h3>
            <ul>
                <li><b>Steep drawdowns:</b> Strategy may be over-leveraged or poorly risk-managed</li>
                <li><b>Long flat periods:</b> Strategy not finding opportunities</li>
                <li><b>Erratic spikes/drops:</b> Inconsistent performance, maybe data issues</li>
                <li><b>Performance concentrated in few trades:</b> Strategy not robust</li>
                <li><b>Downward trend:</b> Strategy losing money over time</li>
            </ul>
        </div>

        <h2 style='color:{GREEN}'>Pattern Recognition</h2>

        <h3>The "Staircase" Pattern</h3>
        <p>Steady upward steps with minor pullbacks - IDEAL. Indicates consistent profitability with controlled risk.</p>

        <h3>The "Mountain" Pattern</h3>
        <p>Sharp rise then sharp fall - DANGER. May indicate over-optimization or data mining bias.</p>

        <h3>The "Flatline" Pattern</h3>
        <p>Long periods with no movement - CONCERN. Strategy may not work in certain market conditions.</p>

        <h3>The "Sawtooth" Pattern</h3>
        <p>Frequent small wins followed by occasional large losses - TYPICAL but ensure win rate supports it.</p>

        <h2 style='color:{GREEN}'>Synthetic Data Impact</h2>
        <p>Amber-shaded regions in the chart indicate periods where synthetic option pricing was used. If most of your equity curve is amber, results are largely theoretical. Focus on periods with real data (non-shaded) for more reliable assessment.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_black_scholes_page(self) -> QWidget:
        """Create the Black-Scholes model guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{INFO}'>📈 Black-Scholes Model</h1>

        <p>The Black-Scholes model is used to generate synthetic option prices when historical data is unavailable.</p>

        <h2 style='color:{GREEN}'>The Formula</h2>

        <div style='background:{BG}; padding:20px; border-radius:8px; font-family:monospace; font-size:11pt; margin:15px 0;'>
            <b>For a Call Option:</b><br>
            C = S·N(d₁) - K·e⁻ʳᵀ·N(d₂)<br><br>

            <b>For a Put Option:</b><br>
            P = K·e⁻ʳᵀ·N(-d₂) - S·N(-d₁)<br><br>

            <b>Where:</b><br>
            d₁ = [ln(S/K) + (r + σ²/2)T] / (σ√T)<br>
            d₂ = d₁ - σ√T<br>
            N(x) = cumulative standard normal distribution
        </div>

        <h2 style='color:{GREEN}'>Parameters</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Symbol</th>
                <th>Parameter</th>
                <th>Source</th>
                <th>Default</th>
            </tr>
            <tr><td><b>S</b></td><td>Spot price</td><td>Current bar close</td><td>—</td></tr>
            <tr><td><b>K</b></td><td>Strike price</td><td>ATM rounded to step</td><td>—</td></tr>
            <tr><td><b>T</b></td><td>Time to expiry</td><td>Days to expiry / 365</td><td>—</td></tr>
            <tr><td><b>r</b></td><td>Risk-free rate</td><td>91-day T-bill rate</td><td>6.5%</td></tr>
            <tr><td><b>σ</b></td><td>Volatility</td><td>VIX or HV</td><td>15%</td></tr>
            <tr><td><b>q</b></td><td>Dividend yield</td><td>Indices</td><td>0%</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Assumptions & Limitations</h2>
        <ul>
            <li><b>European-style exercise:</b> Options can only be exercised at expiry</li>
            <li><b>No dividends:</b> Indices assumed to have no dividend yield</li>
            <li><b>Constant volatility:</b> σ doesn't change over option life</li>
            <li><b>Constant interest rate:</b> r doesn't change</li>
            <li><b>Lognormal returns:</b> Prices follow geometric Brownian motion</li>
            <li><b>No transaction costs:</b> Ignored (handled separately)</li>
            <li><b>Liquid markets:</b> Can buy/sell any quantity at theoretical price</li>
        </ul>

        <p>These assumptions mean synthetic prices may differ from actual market prices, especially for deep ITM/OTM options or during high volatility.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_volatility_page(self) -> QWidget:
        """Create the volatility sources guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>🌪️ Volatility Sources</h1>

        <p>The backtest engine supports two volatility sources for option pricing.</p>

        <h2 style='color:{GREEN}'>Option 1: India VIX (use_vix=True)</h2>

        <h3>What is VIX?</h3>
        <p>The India VIX is a volatility index calculated from NIFTY option prices. It represents the market's expectation of volatility over the next 30 days.</p>

        <h3>Source Priority</h3>
        <ol>
            <li><b>Broker API:</b> If broker provides VIX data (preferred)</li>
            <li><b>NSE Website:</b> Direct fetch from NSE historical data</li>
            <li><b>yfinance:</b> ^INDIAVIX ticker</li>
            <li><b>Default:</b> 15% constant if all sources fail</li>
        </ol>

        <h3>Pros</h3>
        <ul>
            <li>Reflects actual market expectations</li>
            <li>Changes with market sentiment</li>
            <li>More realistic for backtesting</li>
        </ul>

        <h3>Cons</h3>
        <ul>
            <li>Requires internet connection</li>
            <li>Slower startup (fetching data)</li>
            <li>May have gaps in historical data</li>
        </ul>

        <h2 style='color:{GREEN}'>Option 2: Historical Volatility (use_vix=False)</h2>

        <h3>How it's Calculated</h3>
        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace;'>
            Returns = ln(close_t / close_t₁)<br>
            σ_bar = std(returns, lookback=20)<br>
            σ_annual = σ_bar × √(bars_per_year)<br>
            bars_per_year = 252 × (375 / interval_minutes)
        </div>

        <h3>Parameters</h3>
        <ul>
            <li><b>Lookback:</b> 20 bars (configurable in code)</li>
            <li><b>Minimum bars:</b> 5 before trusting HV over default</li>
            <li><b>Default fallback:</b> 15% when insufficient data</li>
        </ul>

        <h3>Pros</h3>
        <ul>
            <li>No internet required</li>
            <li>Fast, no external dependencies</li>
            <li>Always available</li>
        </ul>

        <h3>Cons</h3>
        <ul>
            <li>May not reflect market expectations</li>
            <li>Lags actual volatility changes</li>
            <li>Less realistic for option pricing</li>
        </ul>

        <h2 style='color:{GREEN}'>Recommendations</h2>
        <ul>
            <li>Use VIX for final validation of strategies</li>
            <li>Use HV for quick testing and optimization</li>
            <li>Compare results with both sources to ensure robustness</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_vix_vs_hv_page(self) -> QWidget:
        """Create the VIX vs HV comparison page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>📊 VIX vs Historical Volatility</h1>

        <h2 style='color:{GREEN}'>Key Differences</h2>

        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Aspect</th>
                <th>India VIX</th>
                <th>Historical Volatility (HV)</th>
            </tr>
            <tr>
                <td><b>What it measures</b></td>
                <td>Expected future volatility</td>
                <td>Actual past volatility</td>
            </tr>
            <tr>
                <td><b>Forward/Backward looking</b></td>
                <td>Forward-looking (30 days)</td>
                <td>Backward-looking (20 bars)</td>
            </tr>
            <tr>
                <td><b>Data source</b></td>
                <td>Option prices</td>
                <td>Spot prices</td>
            </tr>
            <tr>
                <td><b>Typical values</b></td>
                <td>10-40% (higher during uncertainty)</td>
                <td>10-30% (smoothed)</td>
            </tr>
            <tr>
                <td><b>Response to events</b></td>
                <td>Immediate (anticipation)</td>
                <td>Delayed (after price moves)</td>
            </tr>
            <tr>
                <td><b>Intraday changes</b></td>
                <td>Can change significantly</td>
                <td>Relatively stable</td>
            </tr>
        </table>

        <h2 style='color:{GREEN}'>When They Diverge</h2>

        <h3>VIX > HV</h3>
        <p><b>Meaning:</b> Market expects higher volatility than recent past</p>
        <p><b>Typical during:</b> Pre-earnings, before major events, uncertainty</p>
        <p><b>Effect on option prices:</b> Options more expensive (higher premiums)</p>

        <h3>VIX < HV</h3>
        <p><b>Meaning:</b> Market expects lower volatility than recent past</p>
        <p><b>Typical during:</b> Post-event calm, range-bound markets</p>
        <p><b>Effect on option prices:</b> Options cheaper (lower premiums)</p>

        <h2 style='color:{GREEN}'>Which is Better for Backtesting?</h2>

        <h3>Use VIX when:</h3>
        <ul>
            <li>Testing strategies that depend on option premium levels</li>
            <li>Validating strategies for live trading</li>
            <li>Market regime matters (high/low vol environments)</li>
        </ul>

        <h3>Use HV when:</h3>
        <ul>
            <li>Quick testing and optimization</li>
            <li>Offline development</li>
            <li>Comparing strategy robustness</li>
        </ul>

        <p><b>Best practice:</b> Test with both and ensure strategy works in both high and low volatility regimes.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_expiry_page(self) -> QWidget:
        """Create the expiry calculation guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{INFO}'>📅 Expiry Calculation</h1>

        <p>The backtest engine automatically determines the correct expiry date for option pricing based on the date of each bar.</p>

        <h2 style='color:{GREEN}'>Weekly Expiry</h2>

        <h3>Logic</h3>
        <ol>
            <li>Determine expiry weekday from derivative (Thursday for NIFTY, Wednesday for BANKNIFTY)</li>
            <li>Find the next expiry on or after current date</li>
            <li>If current time is after expiry (15:30), roll to next week</li>
            <li>Adjust for holidays (move to previous trading day)</li>
        </ol>

        <h3>Example</h3>
        <p>For NIFTY on Tuesday, 2024-01-15:</p>
        <ul>
            <li>Expiry weekday = Thursday (3)</li>
            <li>Days ahead = (3 - 1) % 7 = 2 days</li>
            <li>Expiry date = 2024-01-18 (Thursday)</li>
        </ul>

        <h2 style='color:{GREEN}'>Monthly Expiry</h2>

        <h3>Logic</h3>
        <ol>
            <li>Get monthly expiry for current month (last weekday of month)</li>
            <li>If current date is after expiry, use next month</li>
            <li>Adjust for holidays</li>
        </ol>

        <h3>Example</h3>
        <p>For January 2024:</p>
        <ul>
            <li>Find last Thursday of January = 2024-01-25</li>
            <li>If current date > 2024-01-25, use February expiry</li>
        </ul>

        <h2 style='color:{GREEN}'>Time to Expiry Calculation</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace;'>
            T = max( (expiry_date - current_date).seconds / (252 × 6.25 × 3600), MIN_T )<br>
            MIN_T = 1 / (365 × 96) ≈ 15 minutes
        </div>

        <p><b>Trading year:</b> 252 days × 6.25 hours × 3600 seconds</p>
        <p><b>Minimum T:</b> Prevents division by zero for very short expiries</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_synthetic_generation_page(self) -> QWidget:
        """Create the synthetic price generation guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{WARN}'>⚗️ Synthetic Price Generation</h1>

        <p>When real option data is unavailable, the engine generates synthetic OHLC prices using Black-Scholes.</p>

        <h2 style='color:{GREEN}'>OHLC Generation Logic</h2>

        <h3>Open Price</h3>
        <p>Calculated with T_open = T_close + bar_fraction (slightly more time to expiry)</p>
        <div style='background:{BG}; padding:10px; border-radius:4px; font-family:monospace;'>
            open = BS(spot_open, strike, T_open, r, σ, type)
        </div>

        <h3>Close Price</h3>
        <p>Calculated with actual time to expiry</p>
        <div style='background:{BG}; padding:10px; border-radius:4px; font-family:monospace;'>
            close = BS(spot_close, strike, T_close, r, σ, type)
        </div>

        <h3>High Price</h3>
        <p>Uses the spot extreme that produces highest option value:</p>
        <ul>
            <li><b>CALL:</b> high = BS(spot_high, strike, avg_T, r, σ, "CE")</li>
            <li><b>PUT:</b> high = BS(spot_low, strike, avg_T, r, σ, "PE")</li>
        </ul>

        <h3>Low Price</h3>
        <p>Uses the spot extreme that produces lowest option value:</p>
        <ul>
            <li><b>CALL:</b> low = BS(spot_low, strike, avg_T, r, σ, "CE")</li>
            <li><b>PUT:</b> low = BS(spot_high, strike, avg_T, r, σ, "PE")</li>
        </ul>

        <h2 style='color:{GREEN}'>Bar Fraction</h2>
        <div style='background:{BG}; padding:10px; border-radius:4px; font-family:monospace;'>
            bar_fraction = minutes_per_bar / (252 × 375)
        </div>

        <h2 style='color:{GREEN}'>Price Smoothing</h2>
        <p>All synthetic prices are:</p>
        <ul>
            <li>Rounded to 2 decimal places (Utils.round_off)</li>
            <li>Capped at minimum 0.05 to avoid negative/zero prices</li>
            <li>Adjusted to ensure high ≥ max(open, close) and low ≤ min(open, close)</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_real_data_page(self) -> QWidget:
        """Create the real data priority guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>✅ Real Data Priority</h1>

        <p>The OptionPricer always prioritizes real historical data when available.</p>

        <h2 style='color:{GREEN}'>Data Priority Chain</h2>

        <div style='background:{BG}; padding:20px; border-radius:8px; margin:15px 0;'>
            <ol style='font-size:12pt;'>
                <li><b style='color:{GREEN};'>REAL DATA</b> — If all four OHLC prices are present and positive</li>
                <li><b style='color:{WARN};'>SYNTHETIC (Black-Scholes)</b> — When any price component missing</li>
            </ol>
        </div>

        <h2 style='color:{GREEN}'>Why Real Data is Preferred</h2>
        <ul>
            <li><b>Actual market prices:</b> Reflects real supply/demand</li>
            <li><b>Bid-ask spread effects:</b> Captured in historical data</li>
            <li><b>Volatility smile:</b> Real options price OTM/ITM differently</li>
            <li><b>Market microstructure:</b> Includes real trading dynamics</li>
        </ul>

        <h2 style='color:{GREEN}'>When Real Data is Unavailable</h2>
        <ul>
            <li><b>Expired strikes:</b> Options that no longer trade</li>
            <li><b>Very old dates:</b> Beyond broker's historical coverage</li>
            <li><b>Gaps in data:</b> Missing bars due to connectivity issues</li>
            <li><b>Weekends/holidays:</b> No trading, but we need prices for continuity</li>
        </ul>

        <h2 style='color:{GREEN}'>Identifying Data Source</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Location</th>
                <th>Real Data</th>
                <th>Synthetic</th>
            </tr>
            <tr>
                <td>Trade Log</td>
                <td>✓ (green)</td>
                <td>⚗ (amber)</td>
            </tr>
            <tr>
                <td>Trade row background</td>
                <td>Normal</td>
                <td>Amber-tinted</td>
            </tr>
            <tr>
                <td>Equity curve</td>
                <td>Normal line</td>
                <td>Amber shaded regions</td>
            </tr>
            <tr>
                <td>Data Quality metric</td>
                <td>High %</td>
                <td>Shows R/S count</td>
            </tr>
        </table>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_tp_page(self) -> QWidget:
        """Create the take profit guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>🎯 Take Profit (TP)</h1>

        <h2 style='color:{GREEN}'>What is Take Profit?</h2>
        <p>Take Profit is a limit order that automatically closes a position when the option price rises by a specified percentage.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            TP Price = Entry Price × (1 + TP% / 100)<br>
            Trigger: Option HIGH ≥ TP Price
        </div>

        <p><b>Important:</b> TP checks use the option's <b>HIGH</b> price during the bar, not just the close. This simulates intraday price movement hitting your target.</p>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Entry Price: ₹100</li>
            <li>TP%: 30%</li>
            <li>TP Price = ₹100 × 1.30 = ₹130</li>
            <li>If option HIGH reaches ₹130 or more → TP triggered</li>
            <li>Exit at ₹130 (minus slippage)</li>
        </ul>

        <h2 style='color:{GREEN}'>Best Practices</h2>

        <h3>Choosing TP Percentage</h3>
        <ul>
            <li><b>Conservative:</b> 20-25% (lock in profits quickly)</li>
            <li><b>Moderate:</b> 30-40% (balance profit and duration)</li>
            <li><b>Aggressive:</b> 50%+ (let winners run)</li>
        </ul>

        <h3>Relationship with SL</h3>
        <p>Consider your risk-reward ratio: TP% / SL% should be ≥ 1.5 for positive expectancy.</p>
        <p>Example: TP=30%, SL=20% → RR=1.5:1</p>

        <h2 style='color:{GREEN}'>TP in Different Market Conditions</h2>
        <ul>
            <li><b>Trending markets:</b> Higher TP to capture larger moves</li>
            <li><b>Range-bound:</b> Lower TP to capture quick reversals</li>
            <li><b>High volatility:</b> May need wider TP to avoid early exits</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_sl_page(self) -> QWidget:
        """Create the stop loss guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{RED}'>🛑 Stop Loss (SL)</h1>

        <h2 style='color:{GREEN}'>What is Stop Loss?</h2>
        <p>Stop Loss is a protective order that automatically closes a position when the option price falls by a specified percentage.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            SL Price = Entry Price × (1 - SL% / 100)<br>
            Trigger: Option LOW ≤ SL Price
        </div>

        <p><b>Important:</b> SL checks use the option's <b>LOW</b> price during the bar, not just the close. This protects against intraday price spikes hitting your stop.</p>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Entry Price: ₹100</li>
            <li>SL%: 25%</li>
            <li>SL Price = ₹100 × 0.75 = ₹75</li>
            <li>If option LOW reaches ₹75 or lower → SL triggered</li>
            <li>Exit at ₹75 (minus slippage)</li>
        </ul>

        <h2 style='color:{GREEN}'>Best Practices</h2>

        <h3>Choosing SL Percentage</h3>
        <ul>
            <li><b>Conservative:</b> 10-15% (tight stops, fewer losses but may get stopped out)</li>
            <li><b>Moderate:</b> 20-25% (balance protection and room to breathe)</li>
            <li><b>Aggressive:</b> 30-40% (wide stops, let trades develop)</li>
        </ul>

        <h3>SL Placement Considerations</h3>
        <ul>
            <li><b>Volatility:</b> Wider stops in high volatility</li>
            <li><b>Timeframe:</b> Wider stops for longer timeframes</li>
            <li><b>Technical levels:</b> Consider placing below support/resistance</li>
        </ul>

        <h2 style='color:{GREEN}'>Common Mistakes</h2>
        <ul>
            <li><b>Too tight:</b> Getting stopped out by normal noise</li>
            <li><b>Too wide:</b> Taking larger losses than necessary</li>
            <li><b>Not using SL:</b> Unlimited downside risk</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_trailing_sl_page(self) -> QWidget:
        """Create the trailing stop loss guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>🏃 Trailing Stop Loss</h1>

        <h2 style='color:{GREEN}'>What is a Trailing Stop?</h2>
        <p>A trailing stop moves up with profits, locking in gains while giving the trade room to develop.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            Peak Price = max(previous_peak, current_high)<br>
            Trailing SL Price = Peak Price × (1 - trailing_SL%)<br>
            Trigger: Option LOW ≤ Trailing SL Price
        </div>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Entry Price: ₹100</li>
            <li>Trailing SL%: 15%</li>
            <li>Initial Trailing SL = ₹100 × 0.85 = ₹85</li>
            <li>Price rises to ₹120 → New Peak = ₹120</li>
            <li>New Trailing SL = ₹120 × 0.85 = ₹102</li>
            <li>Price falls to ₹100 (LOW ≤ ₹102) → Triggered</li>
            <li>Exit at ₹102 (locked in profit)</li>
        </ul>

        <h2 style='color:{GREEN}'>Benefits</h2>
        <ul>
            <li><b>Let winners run:</b> No fixed profit target</li>
            <li><b>Lock in profits:</b> Stop moves up with price</li>
            <li><b>Adaptive:</b> Adjusts to market conditions</li>
        </ul>

        <h2 style='color:{GREEN}'>Choosing Trailing SL %</h2>
        <ul>
            <li><b>Tight (5-10%):</b> Quick profit protection, may exit early</li>
            <li><b>Medium (15-20%):</b> Balance protection and trend capture</li>
            <li><b>Wide (25-30%):</b> Let trades breathe, accept bigger pullbacks</li>
        </ul>

        <h2 style='color:{GREEN}'>Combining with Fixed TP/SL</h2>
        <p>You can use trailing SL alongside fixed TP/SL:</p>
        <ul>
            <li><b>Fixed TP:</b> Takes profits at target</li>
            <li><b>Trailing SL:</b> Protects profits if TP not hit</li>
            <li><b>Fixed SL:</b> Initial protection</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_index_sl_page(self) -> QWidget:
        """Create the index-based stop loss guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{ORANGE}'>📉 Index-Based Stop Loss</h1>

        <h2 style='color:{GREEN}'>What is Index SL?</h2>
        <p>Index SL uses spot price movement rather than option price movement to trigger exits. This can be useful when option prices are synthetic or unreliable.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>

        <h3>For CALL Positions</h3>
        <div style='background:{BG}; padding:10px; border-radius:8px; font-family:monospace; margin:10px 0;'>
            Index SL Level = Entry Spot - Index SL Points<br>
            Trigger: Spot LOW ≤ Index SL Level
        </div>

        <h3>For PUT Positions</h3>
        <div style='background:{BG}; padding:10px; border-radius:8px; font-family:monospace; margin:10px 0;'>
            Index SL Level = Entry Spot + Index SL Points<br>
            Trigger: Spot HIGH ≥ Index SL Level
        </div>

        <h2 style='color:{GREEN}'>Example</h2>

        <h3>CALL Example</h3>
        <ul>
            <li>Entry Spot: 18,000</li>
            <li>Index SL: 100 points</li>
            <li>Index SL Level = 18,000 - 100 = 17,900</li>
            <li>If spot LOW reaches 17,900 → Exit triggered</li>
        </ul>

        <h3>PUT Example</h3>
        <ul>
            <li>Entry Spot: 18,000</li>
            <li>Index SL: 100 points</li>
            <li>Index SL Level = 18,000 + 100 = 18,100</li>
            <li>If spot HIGH reaches 18,100 → Exit triggered</li>
        </ul>

        <h2 style='color:{GREEN}'>When to Use Index SL</h2>
        <ul>
            <li><b>Synthetic option prices:</b> When option data is unreliable</li>
            <li><b>Directional strategies:</b> When you want to exit based on spot move</li>
            <li><b>Combination with option SL:</b> Use whichever hits first</li>
        </ul>

        <h2 style='color:{GREEN}'>Choosing Index SL Points</h2>
        <ul>
            <li><b>NIFTY:</b> 50-150 points typical</li>
            <li><b>BANKNIFTY:</b> 100-300 points typical</li>
            <li>Should be larger than normal daily range to avoid noise</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_max_hold_page(self) -> QWidget:
        """Create the max hold bars guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>⏱️ Max Hold Bars</h1>

        <h2 style='color:{GREEN}'>What is Max Hold?</h2>
        <p>Max Hold Bars forces an exit after a specified number of bars, regardless of price or signals. This prevents trades from being held indefinitely.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            Bars in Trade counter increments each bar<br>
            If Bars in Trade ≥ Max Hold Bars → Exit at option CLOSE price
        </div>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Max Hold Bars = 10 (for 5-minute bars)</li>
            <li>Entry at 10:00</li>
            <li>Bars counted: 10:05 (1), 10:10 (2), ..., 10:50 (10)</li>
            <li>At 10:50 bar close, position is forced to exit</li>
            <li>Exit price = option CLOSE at 10:50</li>
        </ul>

        <h2 style='color:{GREEN}'>Why Use Max Hold?</h2>
        <ul>
            <li><b>Time-based exits:</b> Prevents holding through unfavorable periods</li>
            <li><b>Signal decay:</b> Assumes signals lose relevance over time</li>
            <li><b>Capital efficiency:</b> Frees up capital for new opportunities</li>
            <li><b>Risk management:</b> Limits exposure duration</li>
        </ul>

        <h2 style='color:{GREEN}'>Choosing Max Hold Values</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Timeframe</th>
                <th>Conservative</th>
                <th>Moderate</th>
                <th>Aggressive</th>
            </tr>
            <tr><td><b>1-min</b></td><td>15-30 bars</td><td>30-60 bars</td><td>60-120 bars</td></tr>
            <tr><td><b>5-min</b></td><td>6-12 bars</td><td>12-24 bars</td><td>24-48 bars</td></tr>
            <tr><td><b>15-min</b></td><td>4-8 bars</td><td>8-16 bars</td><td>16-32 bars</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Considerations</h2>
        <ul>
            <li>Shorter holds → More exits, potentially more slippage/costs</li>
            <li>Longer holds → May miss reversals, larger drawdowns</li>
            <li>Match to expected trade duration from backtesting</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_risk_reward_page(self) -> QWidget:
        """Create the risk-reward ratios guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>📊 Risk-Reward Ratios</h1>

        <h2 style='color:{GREEN}'>What is Risk-Reward Ratio?</h2>
        <p>Risk-Reward Ratio (RR) compares the potential profit to potential loss on a trade.</p>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            RR Ratio = Take Profit % / Stop Loss %
        </div>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>TP% = 30%</li>
            <li>SL% = 20%</li>
            <li>RR = 30/20 = 1.5:1</li>
            <li>Meaning: You risk 1 to make 1.5</li>
        </ul>

        <h2 style='color:{GREEN}'>Required Win Rate by RR</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>RR Ratio</th>
                <th>Breakeven Win Rate</th>
                <th>Good Win Rate (Profit Factor >1.5)</th>
            </tr>
            <tr><td><b>1:1</b></td><td>50%</td><td>60%</td></tr>
            <tr><td><b>1.5:1</b></td><td>40%</td><td>50%</td></tr>
            <tr><td><b>2:1</b></td><td>33%</td><td>43%</td></tr>
            <tr><td><b>3:1</b></td><td>25%</td><td>33%</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Common RR Configurations</h2>

        <h3>Conservative (RR 2:1)</h3>
        <ul>
            <li>TP=40%, SL=20%</li>
            <li>Need only 33% win rate to break even</li>
            <li>Good for trend-following strategies</li>
        </ul>

        <h3>Moderate (RR 1.5:1)</h3>
        <ul>
            <li>TP=30%, SL=20%</li>
            <li>Need 40% win rate</li>
            <li>Balanced approach</li>
        </ul>

        <h3>Aggressive (RR 1:1)</h3>
        <ul>
            <li>TP=20%, SL=20%</li>
            <li>Need >50% win rate</li>
            <li>Scalping, high-frequency strategies</li>
        </ul>

        <h2 style='color:{GREEN}'>Choosing Your RR</h2>
        <ul>
            <li><b>Higher RR:</b> Fewer winners, but winners are larger</li>
            <li><b>Lower RR:</b> More winners, but winners are smaller</li>
            <li><b>Match to strategy:</b> Trend following → higher RR, mean reversion → lower RR</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_sideway_zone_page(self) -> QWidget:
        """Create the sideway zone skip guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{YELLOW}'>⏸️ Sideway Zone Skip</h1>

        <h2 style='color:{GREEN}'>What is the Sideway Zone?</h2>
        <p>The sideway zone (12:00 PM to 2:00 PM) is a period of typically lower volatility and range-bound movement in Indian markets, especially in index options.</p>

        <h2 style='color:{GREEN}'>Why Skip It?</h2>
        <ul>
            <li><b>Lower volatility:</b> Fewer profitable opportunities</li>
            <li><b>Range-bound movement:</b> Increased chance of whipsaws</li>
            <li><b>Lunch hour effect:</b> Reduced participation</li>
            <li><b>Better risk-reward:</b> Avoid low-probability periods</li>
        </ul>

        <h2 style='color:{GREEN}'>How It Works</h2>
        <p>When enabled, the engine skips signal evaluation for bars where:</p>
        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            bar_time.time() between 12:00 and 14:00 → Skip with reason "SIDEWAY"
        </div>

        <p><b>Important:</b> Existing positions are NOT affected. Only new entries are skipped.</p>

        <h2 style='color:{GREEN}'>Should You Enable It?</h2>

        <h3>YES, enable when:</h3>
        <ul>
            <li>Trading index options (NIFTY, BANKNIFTY)</li>
            <li>Using shorter timeframes (1-15 minutes)</li>
            <li>Strategy relies on momentum/breakouts</li>
        </ul>

        <h3>NO, disable when:</h3>
        <ul>
            <li>Trading stocks or other instruments</li>
            <li>Using longer timeframes (60m+)</li>
            <li>Strategy specifically designed for range-bound markets</li>
        </ul>

        <h2 style='color:{GREEN}'>Impact on Results</h2>
        <ul>
            <li><b>Win rate:</b> Usually improves (avoiding low-quality setups)</li>
            <li><b>Trade count:</b> Reduces by ~20-30% (2 hours of 6.25 hour day)</li>
            <li><b>Overall P&L:</b> Typically improves due to better trade quality</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_slippage_page(self) -> QWidget:
        """Create the slippage guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{RED}'>📉 Slippage</h1>

        <h2 style='color:{GREEN}'>What is Slippage?</h2>
        <p>Slippage is the difference between the expected price of a trade and the price at which the trade is actually executed.</p>

        <h2 style='color:{GREEN}'>Why Slippage Happens</h2>
        <ul>
            <li><b>Market movement:</b> Price changes between order and execution</li>
            <li><b>Liquidity:</b> Not enough orders at desired price</li>
            <li><b>Order size:</b> Large orders move the market</li>
            <li><b>Latency:</b> Delay in order transmission</li>
        </ul>

        <h2 style='color:{GREEN}'>How It's Modeled</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            Entry Price = Option Price × (1 + Slippage%)<br>
            Exit Price = Option Price × (1 - Slippage%)
        </div>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Option Price: ₹100</li>
            <li>Slippage: 0.25%</li>
            <li>Entry Price = ₹100 × 1.0025 = ₹100.25</li>
            <li>Exit Price = ₹100 × 0.9975 = ₹99.75</li>
            <li>Round-trip cost = ₹0.50 per option (0.5%)</li>
        </ul>

        <h2 style='color:{GREEN}'>Typical Slippage Values</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Instrument</th>
                <th>Liquid</th>
                <th>Normal</th>
                <th>Illiquid</th>
            </tr>
            <tr><td><b>NIFTY Options</b></td><td>0.1-0.2%</td><td>0.2-0.3%</td><td>0.3-0.5%</td></tr>
            <tr><td><b>BANKNIFTY Options</b></td><td>0.15-0.25%</td><td>0.25-0.35%</td><td>0.35-0.6%</td></tr>
            <tr><td><b>Stock Options</b></td><td>0.2-0.3%</td><td>0.3-0.5%</td><td>0.5-1.0%</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Impact on Strategy</h2>
        <ul>
            <li><b>High slippage:</b> Reduces profitability, especially for frequent traders</li>
            <li><b>Low slippage:</b> More realistic for liquid instruments</li>
            <li><b>Zero slippage:</b> Unrealistic, only for theoretical testing</li>
        </ul>

        <h2 style='color:{GREEN}'>Recommendations</h2>
        <ul>
            <li>Use 0.25% as default for index options</li>
            <li>Test with higher slippage (0.5%) to stress-test strategy</li>
            <li>Compare results with/without slippage to see impact</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_brokerage_page(self) -> QWidget:
        """Create the brokerage guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>💸 Brokerage</h1>

        <h2 style='color:{GREEN}'>What is Brokerage?</h2>
        <p>Brokerage is the fee charged by your broker for executing trades.</p>

        <h2 style='color:{GREEN}'>How It's Calculated</h2>

        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            Total Brokerage = Brokerage per Lot × Lots × 2<br>
            (×2 because both entry and exit are charged)
        </div>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Brokerage per Lot: ₹40</li>
            <li>Lots: 2</li>
            <li>Total Brokerage = ₹40 × 2 × 2 = ₹160 per round-trip</li>
        </ul>

        <h2 style='color:{GREEN}'>Brokerage by Broker</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Broker</th>
                <th>Options Brokerage</th>
                <th>Notes</th>
            </tr>
            <tr><td><b>Zerodha</b></td><td>₹20 per lot</td><td>Plus exchange fees</td></tr>
            <tr><td><b>Dhan</b></td><td>₹20 per lot</td><td>Flat structure</td></tr>
            <tr><td><b>Angel One</b></td><td>₹20 per lot</td><td>For active plan</td></tr>
            <tr><td><b>Upstox</b></td><td>₹20 per lot</td><td>Standard plan</td></tr>
            <tr><td><b>Groww</b></td><td>₹20 per lot</td><td>Options</td></tr>
            <tr><td><b>ICICI Direct</b></td><td>0.25-0.50%</td><td>Percentage based</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Additional Charges</h2>
        <p><i>Note: Our brokerage model is simplified. Real trading includes:</i></p>
        <ul>
            <li><b>Exchange fees:</b> ₹ per crore turnover</li>
            <li><b>SEBI charges:</b> ₹ per crore turnover</li>
            <li><b>GST:</b> 18% on brokerage</li>
            <li><b>Stamp duty:</b> State-specific</li>
        </ul>

        <h2 style='color:{GREEN}'>Impact on Strategy</h2>
        <ul>
            <li><b>High-frequency strategies:</b> Brokerage can kill profitability</li>
            <li><b>Small profits:</b> May turn into losses after brokerage</li>
            <li><b>Fewer trades:</b> More selective strategies fare better</li>
        </ul>

        <h2 style='color:{GREEN}'>Recommendations</h2>
        <ul>
            <li>Use ₹40 per lot as conservative estimate</li>
            <li>Check your actual broker's charges</li>
            <li>Include in backtest - it matters!</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_position_sizing_page(self) -> QWidget:
        """Create the position sizing guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>📊 Position Sizing</h1>

        <h2 style='color:{GREEN}'>What is Position Sizing?</h2>
        <p>Position sizing determines how many contracts/lots to trade based on your capital and risk tolerance.</p>

        <h2 style='color:{GREEN}'>Components</h2>

        <h3>Lot Size</h3>
        <ul>
            <li><b>NIFTY:</b> 50 shares per lot</li>
            <li><b>BANKNIFTY:</b> 25 shares per lot</li>
            <li><b>FINNIFTY:</b> 40 shares per lot</li>
            <li><b>MIDCPNIFTY:</b> 75 shares per lot</li>
            <li><b>SENSEX:</b> 10 shares per lot</li>
        </ul>

        <h3>Number of Lots</h3>
        <p>Total contracts = Lot Size × Number of Lots</p>

        <h2 style='color:{GREEN}'>Position Value</h2>
        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            Position Value = Option Premium × Lot Size × Lots<br>
            Example: ₹100 × 50 × 2 = ₹10,000
        </div>

        <h2 style='color:{GREEN}'>Risk Per Trade</h2>
        <div style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; margin:15px 0;'>
            Risk Amount = Position Value × SL%<br>
            Risk % of Capital = (Risk Amount / Capital) × 100
        </div>

        <h2 style='color:{GREEN}'>Example</h2>
        <ul>
            <li>Capital: ₹100,000</li>
            <li>Option Premium: ₹100</li>
            <li>Lot Size: 50, Lots: 2</li>
            <li>Position Value = ₹100 × 50 × 2 = ₹10,000</li>
            <li>SL%: 25% → Risk Amount = ₹10,000 × 0.25 = ₹2,500</li>
            <li>Risk % = 2.5% of capital</li>
        </ul>

        <h2 style='color:{GREEN}'>Position Sizing Rules</h2>

        <h3>Fixed Fractional</h3>
        <p>Risk fixed % of capital per trade (e.g., 2%):</p>
        <ul>
            <li>Risk per trade = Capital × 2%</li>
            <li>Position size = Risk per trade / (Premium × SL%)</li>
        </ul>

        <h3>Kelly Criterion</h3>
        <p>Optimal sizing based on win rate and RR:</p>
        <ul>
            <li>Kelly % = Win Rate - (Loss Rate / RR)</li>
            <li>Usually use half-Kelly for safety</li>
        </ul>

        <h2 style='color:{GREEN}'>Recommendations</h2>
        <ul>
            <li>Risk 1-2% per trade maximum</li>
            <li>Start with 1 lot for testing</li>
            <li>Scale up gradually with confidence</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_capital_page(self) -> QWidget:
        """Create the capital management guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>💵 Capital Management</h1>

        <h2 style='color:{GREEN}'>Initial Capital</h2>
        <p>Starting capital for the backtest. All P&L calculations and drawdowns are based on this.</p>

        <h2 style='color:{GREEN}'>Key Metrics Based on Capital</h2>

        <h3>Return on Capital</h3>
        <div style='background:{BG}; padding:10px; border-radius:8px; font-family:monospace; margin:10px 0;'>
            ROC = (Net P&L / Initial Capital) × 100%
        </div>

        <h3>Drawdown %</h3>
        <div style='background:{BG}; padding:10px; border-radius:8px; font-family:monospace; margin:10px 0;'>
            Drawdown % = (Max Drawdown / Initial Capital) × 100%
        </div>

        <h2 style='color:{GREEN}'>What's Good?</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Metric</th>
                <th>Excellent</th>
                <th>Good</th>
                <th>Poor</th>
            </tr>
            <tr>
                <td><b>Monthly Return</b></td>
                <td>>15%</td>
                <td>8-15%</td>
                <td><5%</td>
            </tr>
            <tr>
                <td><b>Max Drawdown</b></td>
                <td><10%</td>
                <td>10-20%</td>
                <td>>20%</td>
            </tr>
            <tr>
                <td><b>Sharpe Ratio</b></td>
                <td>>2.0</td>
                <td>1.0-2.0</td>
                <td><1.0</td>
            </tr>
        </table>

        <h2 style='color:{GREEN}'>Capital Allocation Considerations</h2>

        <h3>Margin Requirements</h3>
        <p>Options trading requires margin. Typically:</p>
        <ul>
            <li><b>NIFTY ATM option:</b> ₹30,000-50,000 per lot</li>
            <li><b>BANKNIFTY ATM option:</b> ₹60,000-100,000 per lot</li>
        </ul>

        <h3>Practical Capital Minimums</h3>
        <ul>
            <li><b>1 lot NIFTY:</b> ₹50,000 minimum</li>
            <li><b>1 lot BANKNIFTY:</b> ₹100,000 minimum</li>
            <li><b>Multiple lots:</b> Proportionally more</li>
        </ul>

        <h2 style='color:{GREEN}'>Reinvestment</h2>
        <p>The backtest compounds profits automatically (equity curve includes all P&L). This simulates reinvesting profits.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_execution_interval_page(self) -> QWidget:
        """Create the execution interval guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>⚡ Execution Intervals</h1>

        <h2 style='color:{GREEN}'>What is Execution Interval?</h2>
        <p>The execution interval determines the candle size used for signal evaluation and trade execution.</p>

        <h2 style='color:{GREEN}'>How It Works</h2>
        <ol>
            <li>Spot data is always fetched at 1-minute resolution</li>
            <li>Data is resampled to your chosen interval</li>
            <li>Signals are evaluated on each resampled bar</li>
            <li>Entries/exits occur at bar boundaries</li>
        </ol>

        <h2 style='color:{GREEN}'>Interval Comparison</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Interval</th>
                <th>Bars/Day</th>
                <th>Pros</th>
                <th>Cons</th>
            </tr>
            <tr>
                <td><b>1-minute</b></td>
                <td>375</td>
                <td>Maximum signals, precise entries</td>
                <td>Noisy, more false signals</td>
            </tr>
            <tr>
                <td><b>5-minute</b></td>
                <td>75</td>
                <td>Balanced, less noise</td>
                <td>Default, good for most</td>
            </tr>
            <tr>
                <td><b>15-minute</b></td>
                <td>25</td>
                <td>Cleaner trends, fewer false signals</td>
                <td>Fewer trades, slower response</td>
            </tr>
            <tr>
                <td><b>30-minute</b></td>
                <td>12</td>
                <td>Swing trading, major moves only</td>
                <td>Very few signals</td>
            </tr>
        </table>

        <h2 style='color:{GREEN}'>Choosing Your Interval</h2>

        <h3>By Trading Style</h3>
        <ul>
            <li><b>Scalping:</b> 1-2 minutes</li>
            <li><b>Day trading:</b> 5-15 minutes</li>
            <li><b>Swing trading:</b> 30-60 minutes</li>
        </ul>

        <h3>By Strategy Type</h3>
        <ul>
            <li><b>Momentum:</b> 5-15 minutes</li>
            <li><b>Mean reversion:</b> 1-5 minutes</li>
            <li><b>Trend following:</b> 15-30 minutes</li>
        </ul>

        <h2 style='color:{GREEN}'>Important Notes</h2>
        <ul>
            <li>Shorter intervals = more trades, more slippage/brokerage</li>
            <li>Longer intervals = fewer trades, potentially larger moves</li>
            <li>Test multiple intervals to find what suits your strategy</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_export_page(self) -> QWidget:
        """Create the export results guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📤 Export Results</h1>

        <h2 style='color:{GREEN}'>What Can Be Exported?</h2>

        <h3>From Strategy Analysis Tab</h3>
        <ul>
            <li><b>Export Timeframe:</b> Save current timeframe as CSV</li>
            <li><b>Export All:</b> Save all selected timeframes</li>
        </ul>

        <h3>Exported Data Includes</h3>
        <ul>
            <li>Timestamp</li>
            <li>Spot price</li>
            <li>Signal</li>
            <li>Overall confidence</li>
            <li>Per-group confidence (BUY_CALL, BUY_PUT, etc.)</li>
            <li>Indicator values (last and previous)</li>
            <li>Rule pass rates per group</li>
        </ul>

        <h2 style='color:{GREEN}'>Auto-Export Feature</h2>
        <p>In the Execution tab, you can enable "Auto-export analysis after run". When checked:</p>
        <ol>
            <li>After backtest completes, you're prompted for a directory</li>
            <li>All selected timeframes are automatically saved as CSV files</li>
            <li>Files are named: [StrategyName]_[Timeframe]_[Timestamp].csv</li>
        </ol>

        <h2 style='color:{GREEN}'>Using Exported Data</h2>

        <h3>Further Analysis</h3>
        <ul>
            <li>Import into Excel/Python for custom analysis</li>
            <li>Create custom charts and visualizations</li>
            <li>Build machine learning models on signal data</li>
            <li>Compare multiple backtest runs</li>
        </ul>

        <h3>Sample Analysis Ideas</h3>
        <ul>
            <li>Signal distribution by time of day</li>
            <li>Confidence vs actual outcome correlation</li>
            <li>Indicator performance breakdown</li>
            <li>Rule effectiveness analysis</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_import_page(self) -> QWidget:
        """Create the import configurations guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>📥 Import Configurations</h1>

        <h2 style='color:{GREEN}'>What Can Be Imported?</h2>
        <p>Currently, the backtest window itself doesn't have direct import/export, but you can:</p>
        <ul>
            <li>Import strategies via the Strategy Editor</li>
            <li>Save/load backtest configurations programmatically</li>
        </ul>

        <h2 style='color:{GREEN}'>Sharing Backtest Configurations</h2>

        <h3>Via Strategy JSON</h3>
        <p>Strategies contain all signal rules and can be exported/imported:</p>
        <ol>
            <li>In Strategy Editor, select your strategy</li>
            <li>Click "📤 Export" to save as JSON</li>
            <li>Share the JSON file with others</li>
            <li>They import via "📥 Import" in Strategy Editor</li>
        </ol>

        <h3>Backtest Parameters</h3>
        <p>To share full backtest configurations, you can:</p>
        <ul>
            <li>Take screenshots of your settings</li>
            <li>Document parameters in a text file</li>
            <li>Share the strategy + parameter documentation</li>
        </ul>

        <h2 style='color:{GREEN}'>Future Features</h2>
        <p><i>Coming in future updates:</i></p>
        <ul>
            <li>Save/load complete backtest configurations</li>
            <li>Batch testing from configuration files</li>
            <li>Export full results package (CSV + charts)</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_batch_testing_page(self) -> QWidget:
        """Create the batch testing guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>🔄 Batch Testing</h1>

        <h2 style='color:{GREEN}'>What is Batch Testing?</h2>
        <p>Batch testing allows you to run multiple backtests with different parameters automatically.</p>

        <h2 style='color:{GREEN}'>Current Capabilities</h2>
        <p>The backtest window currently runs one test at a time. For batch testing, you can:</p>

        <h3>Manual Approach</h3>
        <ol>
            <li>Run backtest with initial parameters</li>
            <li>Export results (Strategy Analysis tab)</li>
            <li>Adjust parameters</li>
            <li>Repeat</li>
            <li>Compare exported CSVs</li>
        </ol>

        <h3>Scripted Approach (Advanced)</h3>
        <p>You can create Python scripts to:</p>
        <ul>
            <li>Iterate over parameter combinations</li>
            <li>Run BacktestEngine programmatically</li>
            <li>Collect and analyze results</li>
        </ul>

        <h2 style='color:{GREEN}'>Parameters to Test</h2>

        <h3>Strategy Parameters</h3>
        <ul>
            <li>Different rule configurations</li>
            <li>Confidence thresholds (0.5, 0.6, 0.7)</li>
            <li>Rule weights</li>
        </ul>

        <h3>Risk Parameters</h3>
        <ul>
            <li>TP% (20%, 30%, 40%)</li>
            <li>SL% (15%, 20%, 25%)</li>
            <li>Trailing SL% (10%, 15%, 20%)</li>
            <li>Index SL points</li>
        </ul>

        <h3>Timeframes</h3>
        <ul>
            <li>Execution intervals (1m, 5m, 15m)</li>
            <li>Analysis timeframes</li>
        </ul>

        <h2 style='color:{GREEN}'>Future Features</h2>
        <p><i>Coming in future updates:</i></p>
        <ul>
            <li>Built-in parameter optimizer</li>
            <li>Walk-forward analysis</li>
            <li>Monte Carlo simulation</li>
            <li>Batch test queue</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_errors_page(self) -> QWidget:
        """Create the common errors guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{RED}'>❌ Common Errors</h1>

        <table width='100%' border='1' cellpadding='12' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Error</th>
                <th>Cause</th>
                <th>Solution</th>
            </tr>
            <tr>
                <td><b>"Could not fetch spot history"</b></td>
                <td>Broker connection issue or no data for date range</td>
                <td>Check broker connection, expand date range, ensure market was open</td>
            </tr>
            <tr>
                <td><b>"No debug data available"</b></td>
                <td>debug_candles=False in config</td>
                <td>Enable in config or ensure backtest completed successfully</td>
            </tr>
            <tr>
                <td><b>Zero trades / no entry attempts</b></td>
                <td>Strategy rules not firing, or filtered out</td>
                <td>
                    - Check strategy has rules and is enabled<br>
                    - Verify min confidence threshold not too high<br>
                    - Ensure enough warmup bars (need 15+)<br>
                    - Check sideway zone skip not eating all bars<br>
                    - Verify market hours (9:15-15:30)
                </td>
            </tr>
            <tr>
                <td><b>All trades show ⚗ (synthetic)</b></td>
                <td>No real option data available</td>
                <td>This is normal for expired strikes. Results are theoretical but still useful.</td>
            </tr>
            <tr>
                <td><b>Backtest very slow</b></td>
                <td>Large date range or many analysis timeframes</td>
                <td>Reduce date range, select fewer timeframes, or use HV instead of VIX</td>
            </tr>
            <tr>
                <td><b>Equity curve flat/missing</b></td>
                <td>No trades or all trades skipped</td>
                <td>Check entry conditions and filters</td>
            </tr>
            <tr>
                <td><b>Strategy analysis tab empty</b></td>
                <td>Analysis timeframes not selected or no data</td>
                <td>Select at least one timeframe, ensure debug_candles=True</td>
            </tr>
            <tr>
                <td><b>Index SL not working</b></td>
                <td>Entry spot not stored correctly</td>
                <td>Check that _bt_spot_entry is being set on entry</td>
            </tr>
        </table>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_debugging_page(self) -> QWidget:
        """Create the debugging tips guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>🔍 Debugging Tips</h1>

        <h2 style='color:{GREEN}'>1. Use Candle Debug Tab</h2>
        <p>The most powerful debugging tool. Shows every bar with:</p>
        <ul>
            <li>Signal evaluation details</li>
            <li>Per-rule pass/fail status</li>
            <li>Indicator values</li>
            <li>Skip reasons</li>
        </ul>

        <h2 style='color:{GREEN}'>2. Check Skip Reasons</h2>
        <p>Filter the Candle Debug tab by "Skip" column to see why bars are being skipped:</p>
        <ul>
            <li><b>SIDEWAY:</b> During 12:00-14:00 (if enabled)</li>
            <li><b>MARKET_CLOSED:</b> Outside 9:15-15:30</li>
            <li><b>WARMUP(n/15):</b> Need 15 bars for indicators to warm up</li>
        </ul>

        <h2 style='color:{GREEN}'>3. Verify Signal Groups</h2>
        <p>In the Strategy Analysis tab, check:</p>
        <ul>
            <li>Are groups enabled? (checkbox in editor)</li>
            <li>Is confidence above threshold? (min confidence setting)</li>
            <li>Are rules actually evaluating? (check per-rule results)</li>
        </ul>

        <h2 style='color:{GREEN}'>4. Check Logs</h2>
        <p>The backtest engine outputs detailed DEBUG logs when logger level is set appropriately:</p>
        <pre style='background:{BG}; padding:10px; border-radius:4px;'>
import logging
logging.getLogger('backtest.backtest_engine').setLevel(logging.DEBUG)</pre>

        <h2 style='color:{GREEN}'>5. Synthetic Data Issues</h2>
        <p>If synthetic prices seem wrong:</p>
        <ul>
            <li>Check VIX/HV values (are they reasonable?)</li>
            <li>Verify time to expiry calculation</li>
            <li>Check strike rounding (should be ATM)</li>
        </ul>

        <h2 style='color:{GREEN}'>6. Entry/Exit Not Working</h2>
        <p>Check the action column in Candle Debug:</p>
        <ul>
            <li>Is action "BUY_CALL"/"BUY_PUT" when expected?</li>
            <li>Is position flat before entry? (Pos column)</li>
            <li>Are exits being triggered by TP/SL/signal?</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_log_analysis_page(self) -> QWidget:
        """Create the log analysis guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>📊 Log Analysis</h1>

        <h2 style='color:{GREEN}'>Understanding Backtest Logs</h2>

        <h3>Per-Candle Assessment Logs</h3>
        <p>When debug logging is enabled, you'll see detailed per-candle output:</p>

        <pre style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace; font-size:9pt;'>
────────────────────────────────────────────────────────
  CANDLE  15-Jan 09:30  |  O=21500.0 H=21520.0 L=21490.0 C=21505.0  |  bars=20  |  pos=FLAT
· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·
  [INDICATORS]  RSI_14=54.32 (prev=53.21)   EMA_20=21480.5 (prev=21475.2)
· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·
  [BUY_CALL]    conf=67%  threshold=60%  rules=2  →  FIRED ✓
    rule[0]  ✓  rsi > 50  w=1.5  LHS=54.32  RHS=50.00  [54.3200 > 50.0000]
    rule[1]  ✓  ema_9 > ema_21  w=2.0  LHS=21480.5  RHS=21475.2  [21480.5000 > 21475.2000]
· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·
  [RESOLVED]  signal=BUY_CALL  |  explanation=BUY_CALL fired with 67% confidence
────────────────────────────────────────────────────────</pre>

        <h3>Key Information</h3>
        <ul>
            <li><b>Candle header:</b> Time, OHLC, position</li>
            <li><b>Indicators:</b> Current and previous values</li>
            <li><b>Per-group:</b> Confidence, threshold, fired status</li>
            <li><b>Per-rule:</b> ✓/✗, values, detail, weight</li>
            <li><b>Resolution:</b> Final signal and explanation</li>
        </ul>

        <h3>End-of-Run Summary</h3>
        <pre style='background:{BG}; padding:15px; border-radius:8px; font-family:monospace;'>
[Backtest] REPLAY COMPLETE - 1500 total bars processed | 
sideway_skip=450 | market_skip=75 | warmup_skip=14 | cooldown_skip=30 | 
no_signal=800 | in_trade=120 | entries=11 | trades=8 | signals={{'BUY_CALL':8, 'WAIT':1420}}</pre>

        <p>This summary helps understand where bars are being consumed.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_performance_page(self) -> QWidget:
        """Create the performance issues guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{YELLOW}'>⚠️ Performance Issues</h1>

        <h2 style='color:{GREEN}'>Why Backtests Can Be Slow</h2>

        <h3>Factors Affecting Speed</h3>
        <ul>
            <li><b>Date range length:</b> More bars = more processing</li>
            <li><b>Number of analysis timeframes:</b> Each adds extra processing</li>
            <li><b>Strategy complexity:</b> More rules = more evaluations</li>
            <li><b>VIX fetching:</b> Network calls slow startup</li>
            <li><b>Indicator complexity:</b> Some indicators are computationally expensive</li>
        </ul>

        <h2 style='color:{GREEN}'>Typical Performance</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'>
                <th>Bars</th>
                <th>Timeframes</th>
                <th>Rules/Group</th>
                <th>Approx Time</th>
            </tr>
            <tr><td>1,000</td><td>1 (execution only)</td><td>2-3</td><td>2-5 seconds</td></tr>
            <tr><td>5,000</td><td>3</td><td>3-5</td><td>15-30 seconds</td></tr>
            <tr><td>10,000</td><td>5</td><td>5-10</td><td>1-2 minutes</td></tr>
            <tr><td>50,000</td><td>5</td><td>5-10</td><td>5-10 minutes</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Optimization Tips</h2>

        <h3>1. Reduce Date Range</h3>
        <p>Test on 30-60 days first, expand only after strategy is validated.</p>

        <h3>2. Limit Analysis Timeframes</h3>
        <p>Select only the timeframes you actually need for analysis.</p>

        <h3>3. Use HV Instead of VIX</h3>
        <p>Historical volatility mode is much faster (no network calls).</p>

        <h3>4. Simplify Rules</h3>
        <p>Fewer rules = faster evaluation. Start simple, add complexity gradually.</p>

        <h3>5. Increase Execution Interval</h3>
        <p>5-minute bars have 75 bars/day vs 375 for 1-minute (5x fewer bars).</p>

        <h2 style='color:{GREEN}'>Progress Indicators</h2>
        <p>The progress bar updates every 50 bars. If it stalls:</p>
        <ul>
            <li>Check if VIX fetch is taking time (visible in startup logs)</li>
            <li>Check for excessive logging (set level to WARNING)</li>
            <li>Check system resources (CPU/memory)</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_faq_page(self) -> QWidget:
        """Create the FAQ page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>❓ Frequently Asked Questions</h1>

        <h3>Q: Why did I get zero trades?</h3>
        <p><b>A:</b> Common reasons:</p>
        <ul>
            <li>Strategy rules aren't firing (check confidence and group logic)</li>
            <li>Min confidence threshold too high</li>
            <li>Not enough warmup bars (need 15+ for indicators)</li>
            <li>Sideway zone skip enabled and all signals in that period</li>
            <li>Market hours filter (only 9:15-15:30)</li>
        </ul>

        <h3>Q: What's the difference between Signal and Action?</h3>
        <p><b>A:</b> 
        <ul>
            <li><b>Signal:</b> Raw output from strategy engine (BUY_CALL, BUY_PUT, etc.)</li>
            <li><b>Action:</b> What the engine actually did after considering position (BUY_CALL if flat, EXIT_CALL if in CALL position, etc.)</li>
        </ul>
        </p>

        <h3>Q: Why are most/all trades synthetic (⚗)?</h3>
        <p><b>A:</b> Historical option data is often unavailable for expired strikes. The engine uses Black-Scholes to generate prices. This is normal and results are still useful for strategy development.</p>

        <h3>Q: How many bars do I need for warmup?</h3>
        <p><b>A:</b> The engine requires at least 15 bars before evaluating signals. This ensures indicators like RSI (14) have enough data.</p>

        <h3>Q: What's the difference between execution interval and analysis timeframes?</h3>
        <p><b>A:</b> 
        <ul>
            <li><b>Execution interval:</b> Used for actual trade decisions (entries/exits)</li>
            <li><b>Analysis timeframes:</b> Separate analysis after backtest, doesn't affect trading</li>
        </ul>
        </p>

        <h3>Q: Can I backtest overnight positions?</h3>
        <p><b>A:</b> No. The engine auto-exits 5 minutes before market close and doesn't model overnight gaps/risk.</p>

        <h3>Q: Why does my equity curve show losses but trade log shows profits?</h3>
        <p><b>A:</b> Check the "Net P&L" column in trade log (includes slippage/brokerage). Gross P&L may be positive but costs turn it negative.</p>

        <h3>Q: How do I export results for Excel?</h3>
        <p><b>A:</b> Use the export buttons in Strategy Analysis tab, or copy/paste from Trade Log table.</p>

        <h3>Q: What's a good win rate?</h3>
        <p><b>A:</b> Depends on risk-reward. With 1.5:1 RR, 40% win rate breaks even. 50-60% is good with proper RR.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_setup_practices_page(self) -> QWidget:
        """Create the setup best practices page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>🎯 Setting Up Backtests - Best Practices</h1>

        <h2 style='color:{GREEN}'>1. Start Simple</h2>
        <ul>
            <li>Begin with 30-60 days of data</li>
            <li>Use default parameters (TP=30%, SL=25%)</li>
            <li>Test with 1 lot only</li>
            <li>Use HV mode for speed</li>
        </ul>

        <h2 style='color:{GREEN}'>2. Verify Basic Functionality</h2>
        <ul>
            <li>Check that trades are happening</li>
            <li>Verify entry/exit logic works</li>
            <li>Ensure costs are applied correctly</li>
        </ul>

        <h2 style='color:{GREEN}'>3. Choose Appropriate Date Range</h2>
        <ul>
            <li><b>Include different market conditions:</b> Trending, ranging, volatile</li>
            <li><b>Avoid:</b> Holiday periods, low-volume days initially</li>
            <li><b>Minimum:</b> 30 days for statistical significance</li>
        </ul>

        <h2 style='color:{GREEN}'>4. Set Realistic Costs</h2>
        <ul>
            <li>Slippage: 0.25% for liquid options</li>
            <li>Brokerage: Match your broker's charges</li>
            <li>Test with higher costs to stress-test</li>
        </ul>

        <h2 style='color:{GREEN}'>5. Enable Candle Debug for First Runs</h2>
        <p>This helps verify signals are firing as expected. Disable for longer runs to save disk space.</p>

        <h2 style='color:{GREEN}'>6. Document Your Setup</h2>
        <p>Keep a log of parameters tested and results for comparison.</p>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_overfitting_page(self) -> QWidget:
        """Create the avoiding overfitting guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{RED}'>📊 Avoiding Overfitting</h1>

        <h2 style='color:{GREEN}'>What is Overfitting?</h2>
        <p>Overfitting occurs when a strategy is too closely tailored to historical data and performs poorly on new data.</p>

        <h2 style='color:{GREEN}'>Warning Signs</h2>
        <ul>
            <li><b>Too good to be true:</b> 90%+ win rates, astronomical Sharpe ratios</li>
            <li><b>Many rules:</b> 20+ rules per group (curse of dimensionality)</li>
            <li><b>Specific parameters:</b> RSI(13) instead of RSI(14), etc.</li>
            <li><b>Performance cliff:</b> Small parameter changes destroy results</li>
            <li><b>Out-of-sample failure:</b> Works great in-sample, fails in validation</li>
        </ul>

        <h2 style='color:{GREEN}'>Prevention Strategies</h2>

        <h3>1. Keep It Simple</h3>
        <ul>
            <li>Start with 2-3 rules per group</li>
            <li>Use standard indicator parameters (14, 20, 50, etc.)</li>
            <li>Add complexity only if justified</li>
        </ul>

        <h3>2. Use Walk-Forward Analysis</h3>
        <ul>
            <li>Train on 70% of data, test on 30%</li>
            <li>Roll forward periodically</li>
            <li>Check consistency across periods</li>
        </ul>

        <h3>3. Test Multiple Time Periods</h3>
        <ul>
            <li>Include bull markets</li>
            <li>Include bear markets</li>
            <li>Include range-bound periods</li>
        </ul>

        <h3>4. Monte Carlo Simulation</h3>
        <p>Randomize entry/exit slightly to see if strategy is robust.</p>

        <h3>5. Out-of-Sample Testing</h3>
        <p>Always reserve some data you never look at until final validation.</p>

        <h2 style='color:{GREEN}'>Good Practices</h2>
        <ul>
            <li>Document every rule addition and why</li>
            <li>Test parameter sensitivity</li>
            <li>Compare with simple benchmarks (buy & hold)</li>
            <li>Be skeptical of amazing results</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_interpreting_results_page(self) -> QWidget:
        """Create the interpreting results best practices page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{GREEN}'>📈 Interpreting Results - Best Practices</h1>

        <h2 style='color:{GREEN}'>1. Look at the Whole Picture</h2>
        <p>Don't focus on any single metric. Consider:</p>
        <ul>
            <li>Net P&L (is it meaningful?)</li>
            <li>Win Rate + Profit Factor (are they consistent?)</li>
            <li>Max Drawdown (can you stomach it?)</li>
            <li>Sharpe Ratio (is risk-adjusted return good?)</li>
            <li>Trade count (statistically significant?)</li>
        </ul>

        <h2 style='color:{GREEN}'>2. Examine the Equity Curve</h2>
        <ul>
            <li><b>Steady uptrend:</b> Good</li>
            <li><b>Large drawdowns:</b> Concern</li>
            <li><b>Flat periods:</b> Strategy may be market-dependent</li>
            <li><b>Late-stage blowup:</b> Risk of ruin</li>
        </ul>

        <h2 style='color:{GREEN}'>3. Analyze Trade Log</h2>
        <ul>
            <li>Are wins larger than losses? (profit factor)</li>
            <li>Are there clusters of losses? (drawdown periods)</li>
            <li>Exit reasons: Too many SL? Too few TP?</li>
            <li>Data quality: Too many synthetic trades?</li>
        </ul>

        <h2 style='color:{GREEN}'>4. Check Strategy Analysis</h2>
        <ul>
            <li>Are signals consistent across timeframes?</li>
            <li>Do high-confidence signals actually win?</li>
            <li>Are certain groups always firing/failing?</li>
        </ul>

        <h2 style='color:{GREEN}'>5. Consider Market Regimes</h2>
        <ul>
            <li>Does strategy work in all conditions?</li>
            <li>Or only in trending/range-bound markets?</li>
            <li>If specialized, can you identify regime?</li>
        </ul>

        <h2 style='color:{GREEN}'>6. Reality Check</h2>
        <ul>
            <li>Would these results hold with real money?</li>
            <li>Are assumptions realistic?</li>
            <li>Is the strategy tradable? (liquidity, slippage)</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_risk_practices_page(self) -> QWidget:
        """Create the risk management best practices page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{RED}'>⚖️ Risk Management - Best Practices</h1>

        <h2 style='color:{GREEN}'>1. Always Use Stop Loss</h2>
        <ul>
            <li>Never trade without a stop loss</li>
            <li>SL should be based on volatility, not arbitrary</li>
            <li>Test different SL levels to find optimal</li>
        </ul>

        <h2 style='color:{GREEN}'>2. Set Realistic Take Profit</h2>
        <ul>
            <li>TP should be achievable based on volatility</li>
            <li>Consider market conditions (trending vs range)</li>
            <li>Test TP levels with backtest</li>
        </ul>

        <h2 style='color:{GREEN}'>3. Risk Per Trade</h2>
        <ul>
            <li><b>Maximum:</b> 2% of capital per trade</li>
            <li><b>Conservative:</b> 1% or less</li>
            <li>Calculate: Risk = Position Value × SL%</li>
        </ul>

        <h2 style='color:{GREEN}'>4. Monitor Drawdown</h2>
        <ul>
            <li><b>Max tolerable:</b> 20% drawdown</li>
            <li>Reduce position size during drawdown</li>
            <li>Consider stopping trading after X% loss</li>
        </ul>

        <h2 style='color:{GREEN}'>5. Diversify</h2>
        <ul>
            <li>Multiple uncorrelated strategies</li>
            <li>Different instruments</li>
            <li>Different timeframes</li>
        </ul>

        <h2 style='color:{GREEN}'>6. Position Sizing Rules</h2>
        <ul>
            <li><b>Fixed fractional:</b> Risk fixed % each trade</li>
            <li><b>Kelly criterion:</b> Optimal growth (use half-Kelly)</li>
            <li><b>Martingale:</b> Avoid (doubling down)</li>
        </ul>

        <h2 style='color:{GREEN}'>7. Use Multiple Exit Types</h2>
        <ul>
            <li>Fixed TP/SL for initial protection</li>
            <li>Trailing SL to lock in profits</li>
            <li>Signal exits for reversal detection</li>
            <li>Time-based exits to limit duration</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_iterative_page(self) -> QWidget:
        """Create the iterative improvement guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>🔄 Iterative Improvement</h1>

        <h2 style='color:{GREEN}'>The Development Cycle</h2>

        <div style='background:{BG}; padding:20px; border-radius:8px; margin:15px 0; text-align:center;'>
            <b>1. IDEA → 2. IMPLEMENT → 3. BACKTEST → 4. ANALYZE → 5. REFINE → (repeat)</b>
        </div>

        <h2 style='color:{GREEN}'>Step 1: Start with a Hypothesis</h2>
        <ul>
            <li>"RSI oversold + EMA uptrend should generate good CALL entries"</li>
            <li>Keep it simple and testable</li>
            <li>Document your hypothesis</li>
        </ul>

        <h2 style='color:{GREEN}'>Step 2: Implement in Strategy Editor</h2>
        <ul>
            <li>Create rules that test your hypothesis</li>
            <li>Start with minimal rules (2-3 per group)</li>
            <li>Use default weights initially</li>
        </ul>

        <h2 style='color:{GREEN}'>Step 3: Run Initial Backtest</h2>
        <ul>
            <li>Use 30-60 days of data</li>
            <li>Default risk parameters</li>
            <li>Enable candle debug</li>
        </ul>

        <h2 style='color:{GREEN}'>Step 4: Analyze Results</h2>
        <ul>
            <li>Check if hypothesis was correct</li>
            <li>Look at individual trades in Candle Debug</li>
            <li>Identify what's working/not working</li>
        </ul>

        <h2 style='color:{GREEN}'>Step 5: Refine</h2>
        <ul>
            <li>Adjust weights based on importance</li>
            <li>Add/remove rules</li>
            <li>Tweak parameters</li>
            <li>Modify risk settings</li>
        </ul>

        <h2 style='color:{GREEN}'>Step 6: Validate</h2>
        <ul>
            <li>Test on out-of-sample data</li>
            <li>Try different market conditions</li>
            <li>Stress-test with higher costs</li>
        </ul>

        <h2 style='color:{GREEN}'>Common Pitfalls to Avoid</h2>
        <ul>
            <li><b>Over-optimizing:</b> Too many tweaks based on one dataset</li>
            <li><b>Curve fitting:</b> Adding rules just to fix past trades</li>
            <li><b>Ignoring costs:</b> Profits may vanish with real slippage</li>
            <li><b>Small sample size:</b> Need 30+ trades for significance</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_mistakes_page(self) -> QWidget:
        """Create the common mistakes guide page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{RED}'>⚠️ Common Mistakes to Avoid</h1>

        <h2 style='color:{GREEN}'>1. Over-Optimization</h2>
        <ul>
            <li><b>Mistake:</b> Tweaking parameters until backtest looks perfect</li>
            <li><b>Result:</b> Strategy fails in live trading</li>
            <li><b>Solution:</b> Test on out-of-sample data, keep it simple</li>
        </ul>

        <h2 style='color:{GREEN}'>2. Ignoring Costs</h2>
        <ul>
            <li><b>Mistake:</b> Not including slippage/brokerage</li>
            <li><b>Result:</b> Profitable in backtest, losing in reality</li>
            <li><b>Solution:</b> Always include realistic costs</li>
        </ul>

        <h2 style='color:{GREEN}'>3. Too Few Trades</h2>
        <ul>
            <li><b>Mistake:</b> Judging strategy on 5-10 trades</li>
            <li><b>Result:</b> Results not statistically significant</li>
            <li><b>Solution:</b> Need 30+ trades for confidence</li>
        </ul>

        <h2 style='color:{GREEN}'>4. Ignoring Market Regimes</h2>
        <ul>
            <li><b>Mistake:</b> Testing only in trending markets</li>
            <li><b>Result:</b> Strategy fails when market changes</li>
            <li><b>Solution:</b> Test across different conditions</li>
        </ul>

        <h2 style='color:{GREEN}'>5. Data Snooping</h2>
        <ul>
            <li><b>Mistake:</b> Using same data for development and validation</li>
            <li><b>Result:</b> Overfitted, won't generalize</li>
            <li><b>Solution:</b> Reserve out-of-sample data</li>
        </ul>

        <h2 style='color:{GREEN}'>6. Ignoring Drawdowns</h2>
        <ul>
            <li><b>Mistake:</b> Only looking at total P&L</li>
            <li><b>Result:</b> Underestimate risk, get stopped out</li>
            <li><b>Solution:</b> Check max drawdown, equity curve</li>
        </ul>

        <h2 style='color:{GREEN}'>7. Too Many Rules</h2>
        <ul>
            <li><b>Mistake:</b> 10+ rules per group</li>
            <li><b>Result:</b> Overfitting, rarely all rules true</li>
            <li><b>Solution:</b> Keep it simple (2-5 rules per group)</li>
        </ul>

        <h2 style='color:{GREEN}'>8. Ignoring Data Quality</h2>
        <ul>
            <li><b>Mistake:</b> Not checking synthetic vs real data</li>
            <li><b>Result:</b> Results may be theoretical</li>
            <li><b>Solution:</b> Check data quality metric</li>
        </ul>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_shortcuts_page(self) -> QWidget:
        """Create the keyboard shortcuts page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{BLUE}'>⌨️ Keyboard Shortcuts</h1>

        <h2 style='color:{GREEN}'>Global Shortcuts</h2>
        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'><th>Shortcut</th><th>Action</th></tr>
            <tr><td><code>Ctrl+R</code></td><td>Run backtest</td></tr>
            <tr><td><code>Ctrl+Shift+R</code></td><td>Stop running backtest</td></tr>
            <tr><td><code>Ctrl+E</code></td><td>Open Strategy Editor</td></tr>
            <tr><td><code>Ctrl+W</code></td><td>Close window</td></tr>
            <tr><td><code>F1</code></td><td>Open help (this tab)</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Navigation Shortcuts</h2>
        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'><th>Shortcut</th><th>Action</th></tr>
            <tr><td><code>Ctrl+Tab</code></td><td>Next results tab</td></tr>
            <tr><td><code>Ctrl+Shift+Tab</code></td><td>Previous results tab</td></tr>
            <tr><td><code>Ctrl+1-6</code></td><td>Switch to settings tab 1-6</td></tr>
            <tr><td><code>Alt+1-5</code></td><td>Switch to results tab 1-5</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Table Navigation (Trade Log, Candle Debug)</h2>
        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'><th>Shortcut</th><th>Action</th></tr>
            <tr><td><code>↑/↓</code></td><td>Navigate rows</td></tr>
            <tr><td><code>PgUp/PgDn</code></td><td>Page up/down</td></tr>
            <tr><td><code>Home/End</code></td><td>First/last row</td></tr>
            <tr><td><code>Enter</code></td><td>Open detail (Candle Debug)</td></tr>
        </table>

        <h2 style='color:{GREEN}'>Search/Filter</h2>
        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'><th>Shortcut</th><th>Action</th></tr>
            <tr><td><code>Ctrl+F</code></td><td>Focus search box</td></tr>
            <tr><td><code>Esc</code></td><td>Clear search / Close popups</td></tr>
        </table>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_glossary_page(self) -> QWidget:
        """Create the glossary page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = f"""
        <h1 style='color:{PURPLE}'>📚 Glossary</h1>

        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{BG_ITEM};'><th>Term</th><th>Definition</th></tr>

            <tr><td><b>ATM (At-The-Money)</b></td><td>Strike price closest to current spot price</td></tr>
            <tr><td><b>Black-Scholes</b></td><td>Mathematical model for pricing options</td></tr>
            <tr><td><b>Brokerage</b></td><td>Fee charged by broker per trade</td></tr>
            <tr><td><b>CALL</b></td><td>Option to buy (bullish position)</td></tr>
            <tr><td><b>Candle Debug</b></td><td>Per-bar signal evaluation data</td></tr>
            <tr><td><b>Confidence</b></td><td>Weighted score indicating signal strength (0-100%)</td></tr>
            <tr><td><b>Drawdown</b></td><td>Peak-to-trough decline in equity</td></tr>
            <tr><td><b>Equity Curve</b></td><td>Graph of account value over time</td></tr>
            <tr><td><b>Execution Interval</b></td><td>Candle size used for trading decisions</td></tr>
            <tr><td><b>Expiry</b></td><td>Date when option contract expires</td></tr>
            <tr><td><b>HV (Historical Volatility)</b></td><td>Volatility calculated from past prices</td></tr>
            <tr><td><b>Index SL</b></td><td>Stop loss based on spot price movement</td></tr>
            <tr><td><b>ITM (In-The-Money)</b></td><td>Option with intrinsic value</td></tr>
            <tr><td><b>Lot Size</b></td><td>Number of shares per contract</td></tr>
            <tr><td><b>OTM (Out-of-The-Money)</b></td><td>Option with no intrinsic value</td></tr>
            <tr><td><b>Overfitting</b></td><td>Strategy too closely tailored to historical data</td></tr>
            <tr><td><b>Profit Factor</b></td><td>Gross profit / gross loss</td></tr>
            <tr><td><b>PUT</b></td><td>Option to sell (bearish position)</td></tr>
            <tr><td><b>Resampling</b></td><td>Converting 1-min data to other timeframes</td></tr>
            <tr><td><b>Risk-Reward Ratio</b></td><td>TP% / SL%</td></tr>
            <tr><td><b>Sharpe Ratio</b></td><td>Risk-adjusted return measure</td></tr>
            <tr><td><b>Sideway Zone</b></td><td>12:00-14:00 period of low volatility</td></tr>
            <tr><td><b>Slippage</b></td><td>Difference between expected and actual fill price</td></tr>
            <tr><td><b>Strike</b></td><td>Price at which option can be exercised</td></tr>
            <tr><td><b>Synthetic Data</b></td><td>Black-Scholes generated option prices</td></tr>
            <tr><td><b>TP (Take Profit)</b></td><td>Limit order to lock in profits</td></tr>
            <tr><td><b>Trailing SL</b></td><td>Stop loss that moves up with profits</td></tr>
            <tr><td><b>VIX</b></td><td>India VIX volatility index</td></tr>
            <tr><td><b>Warmup</b></td><td>Initial bars needed for indicators to stabilize</td></tr>
            <tr><td><b>Win Rate</b></td><td>Percentage of profitable trades</td></tr>
        </table>
        """

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text_edit.setHtml(text)
        layout.addWidget(text_edit)

        return widget

    def _create_text_page(self, title: str, content: str) -> QWidget:
        """Create a simple text page"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_ITEM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px;
                font-size: 11pt;
            }}
        """)
        text.setHtml(f"<h1 style='color:{BLUE};'>{title}</h1>\n\n{content}")
        layout.addWidget(text)

        return widget

    def _connect_navigation(self):
        """Connect navigation tree to content pages"""
        self.nav_tree.itemClicked.connect(self._on_nav_item_clicked)

    def _on_nav_item_clicked(self, item, column):
        """Handle navigation item click"""
        page_name = item.text(0)
        self.show_page(page_name)

    def show_page(self, page_name: str):
        """Show a specific page by name"""
        if page_name in self.pages:
            self.content_stack.setCurrentWidget(self.pages[page_name])
        else:
            # Try to find by partial match
            for name, widget in self.pages.items():
                if page_name in name or name in page_name:
                    self.content_stack.setCurrentWidget(widget)
                    return
            # Default to welcome if not found
            self.content_stack.setCurrentWidget(self.pages.get("welcome"))

    def _filter_navigation(self, text: str):
        """Filter navigation tree based on search text"""
        text = text.lower()
        for i in range(self.nav_tree.topLevelItemCount()):
            top_item = self.nav_tree.topLevelItem(i)
            visible = False

            # Check children
            for j in range(top_item.childCount()):
                child = top_item.child(j)
                child_text = child.text(0).lower()
                if text in child_text or not text:
                    child.setHidden(False)
                    visible = True
                else:
                    child.setHidden(True)

            # Show top level if any child visible or top level matches
            top_text = top_item.text(0).lower()
            if visible or (text and text in top_text):
                top_item.setHidden(False)
            else:
                top_item.setHidden(True)

    def _get_backtesting_overview_content(self) -> str:
        """Get content for the backtesting overview page"""
        return f"""
        <h2>What is Backtesting?</h2>
        <p>Backtesting is the process of testing a trading strategy on historical data to evaluate its performance before risking real money.</p>

        <h3>Why Backtest?</h3>
        <ul>
            <li><b>Validate strategies:</b> See if your ideas actually work</li>
            <li><b>Optimize parameters:</b> Find the best settings</li>
            <li><b>Understand risk:</b> See drawdowns and worst-case scenarios</li>
            <li><b>Build confidence:</b> Before trading with real money</li>
        </ul>

        <h3>Our Backtest Engine Features</h3>
        <ul>
            <li>Realistic option pricing (Black-Scholes with VIX/HV)</li>
            <li>Multi-timeframe analysis</li>
            <li>Comprehensive risk management (TP/SL/trailing/index SL)</li>
            <li>Per-candle debugging</li>
            <li>Cost modeling (slippage, brokerage)</li>
        </ul>

        <h3>Key Concepts</h3>
        <ul>
            <li><b>Spot data:</b> Underlying index prices (NIFTY, BANKNIFTY, etc.)</li>
            <li><b>Option pricing:</b> How option prices are generated</li>
            <li><b>Signal evaluation:</b> Strategy rules determine entries/exits</li>
            <li><b>Position management:</b> How trades are opened/closed</li>
            <li><b>Performance metrics:</b> P&L, win rate, drawdown, etc.</li>
        </ul>
        """

    def _get_first_time_setup_content(self) -> str:
        """Get content for the first-time setup page"""
        return f"""
        <h2>First-Time Setup Guide</h2>

        <h3>Prerequisites</h3>
        <ul>
            <li>Connected to a broker (for spot data)</li>
            <li>At least one strategy created in Strategy Editor</li>
            <li>Internet connection (if using VIX)</li>
        </ul>

        <h3>Step-by-Step Setup</h3>

        <h4>1. Verify Broker Connection</h4>
        <p>Ensure you're connected to your broker in the main TradingGUI. The backtester uses the same broker for spot data.</p>

        <h4>2. Create/Select a Strategy</h4>
        <ul>
            <li>Open Strategy Editor (Ctrl+E)</li>
            <li>Create a new strategy or select an existing one</li>
            <li>Ensure it has at least a few rules</li>
        </ul>

        <h4>3. Configure Backtest</h4>
        <ul>
            <li>Select your strategy in the Strategy tab</li>
            <li>Choose a date range (last 30 days is a good start)</li>
            <li>Set risk parameters (start with TP=30%, SL=25%)</li>
            <li>Set costs (slippage=0.25%, brokerage=40)</li>
            <li>Choose execution interval (5 minutes)</li>
        </ul>

        <h4>4. Run Test</h4>
        <ul>
            <li>Click "▶ Run Backtest"</li>
            <li>Watch progress bar and messages</li>
            <li>Wait for completion</li>
        </ul>

        <h4>5. Review Results</h4>
        <ul>
            <li>Check Overview tab for summary</li>
            <li>Look at Trade Log for individual trades</li>
            <li>Use Candle Debug to verify signals</li>
        </ul>
        """

    def _get_spot_data_content(self) -> str:
        """Get content for the spot data page"""
        return f"""
        <h2>Spot Data & Resampling</h2>

        <h3>Data Source</h3>
        <p>The backtester fetches 1-minute spot data from your connected broker for the selected date range.</p>

        <h3>Resampling Process</h3>
        <ol>
            <li>Raw 1-minute data is fetched from broker</li>
            <li>Data is filtered to market hours (9:15-15:30)</li>
            <li>Resampled to execution interval using OHLC aggregation:
                <ul>
                    <li><b>Open:</b> First open in period</li>
                    <li><b>High:</b> Maximum high in period</li>
                    <li><b>Low:</b> Minimum low in period</li>
                    <li><b>Close:</b> Last close in period</li>
                </ul>
            </li>
        </ol>

        <h3>Example: 1-min → 5-min</h3>
        <p>5 bars of 1-minute data become 1 bar of 5-minute data:</p>
        <pre style='background:{BG}; padding:10px; border-radius:4px;'>
1-min bars: 09:30, 09:31, 09:32, 09:33, 09:34
5-min bar:  09:30-09:34 (open=09:30 open, high=max of 5 highs, 
                         low=min of 5 lows, close=09:34 close)</pre>

        <h3>Important Notes</h3>
        <ul>
            <li>Always use 1-min resolution for maximum flexibility</li>
            <li>Resampling is lossy - you can't reconstruct 1-min from 5-min</li>
            <li>Execution interval must be ≤ analysis timeframes (can't upsample)</li>
        </ul>
        """

    def _get_position_management_content(self) -> str:
        """Get content for the position management page"""
        return f"""
        <h2>Position Management</h2>

        <h3>Position States</h3>
        <ul>
            <li><b>FLAT:</b> No open position</li>
            <li><b>CALL:</b> Long CALL option</li>
            <li><b>PUT:</b> Long PUT option</li>
        </ul>

        <h3>Entry Process</h3>
        <ol>
            <li>Signal engine generates BUY_CALL or BUY_PUT</li>
            <li>If flat, enter position at option close price + slippage</li>
            <li>Store entry details: time, spot, strike, option price</li>
            <li>Initialize trailing stop at entry price</li>
        </ol>

        <h3>Exit Process (Priority Order)</h3>
        <ol>
            <li><b>TP Hit:</b> Option high ≥ entry × (1 + TP%)</li>
            <li><b>SL Hit:</b> Option low ≤ entry × (1 - SL%)</li>
            <li><b>Trailing SL Hit:</b> Option low ≤ peak × (1 - trailing%)</li>
            <li><b>Index SL Hit:</b> Spot moves against position by index points</li>
            <li><b>Max Hold:</b> Bars in trade ≥ limit</li>
            <li><b>Signal Exit:</b> Exit signal received (EXIT_CALL/EXIT_PUT)</li>
            <li><b>Market Close:</b> 5 minutes before end of day</li>
        </ol>

        <h3>Position Tracking</h3>
        <ul>
            <li><b>Bars in trade:</b> Count of bars since entry</li>
            <li><b>Trailing high:</b> Highest option price since entry</li>
            <li><b>Entry strike:</b> Strike locked at entry (doesn't change)</li>
        </ul>
        """

    def load(self, strategy: Dict):
        """Load strategy data (no-op for help tab)"""
        pass

    def collect(self) -> Dict:
        """Collect help tab data (no-op)"""
        return {}