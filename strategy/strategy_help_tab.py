"""
strategy_help_tab.py
====================
Comprehensive Help & Documentation tab for the Strategy Editor.
Separated from main editor file for better maintainability.

FEATURES:
- Interactive documentation with examples
- Searchable navigation tree
- One-click preset and example application
- Troubleshooting guides
- Keyboard shortcuts reference
FULLY INTEGRATED with ThemeManager for dynamic theming.
"""

import logging
from typing import Dict, List, Optional, Any

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFont, QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QStackedWidget, QTextEdit,
    QPushButton, QLineEdit, QSplitter, QScrollArea, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)

from strategy.strategy_presets import get_preset_names, get_preset_rules
from strategy.strategy_manager import strategy_manager
from strategy.indicator_registry import (
    get_suggested_weight, get_indicator_params, get_indicator_category
)

# Rule 13.1: Import theme manager
from gui.theme_manager import theme_manager

logger = logging.getLogger(__name__)


class ThemedMixin:
    """Mixin class to provide theme token shortcuts."""

    @property
    def _c(self):
        return theme_manager.palette

    @property
    def _ty(self):
        return theme_manager.typography

    @property
    def _sp(self):
        return theme_manager.spacing


def get_signal_meta():
    """Get signal metadata with theme colors."""
    c = theme_manager.palette
    return {
        "BUY_CALL": ("📈", c.GREEN, "BUY CALL"),
        "BUY_PUT": ("📉", c.BLUE, "BUY PUT"),
        "EXIT_CALL": ("🔴", c.RED, "EXIT CALL"),
        "EXIT_PUT": ("🟠", c.ORANGE, "EXIT PUT"),
        "HOLD": ("⏸", c.YELLOW, "HOLD"),
    }


class _ExampleCard(QFrame, ThemedMixin):
    """Card widget for displaying an example rule"""

    def __init__(self, example_name: str, signal: str, rules: list, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)
            self.example_name = example_name
            self.signal = signal
            self.rules = rules
            self.parent_tab = parent

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._init_ui()
            self.apply_theme()

        except Exception as e:
            logger.error(f"[_ExampleCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.example_name = ""
        self.signal = ""
        self.rules = []
        self.parent_tab = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the card."""
        try:
            c = self._c
            sp = self._sp

            self.setStyleSheet(f"""
                QFrame {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_MD}px;
                    padding: {sp.PAD_MD}px;
                }}
                QFrame:hover {{
                    border: {sp.SEPARATOR}px solid {c.BLUE};
                }}
            """)
        except Exception as e:
            logger.error(f"[_ExampleCard.apply_theme] Failed: {e}", exc_info=True)

    def _init_ui(self):
        c = self._c
        sp = self._sp
        ty = self._ty
        signal_meta = get_signal_meta()
        signal_color = signal_meta.get(self.signal, ("", c.TEXT_DIM, ""))[1]

        layout = QVBoxLayout(self)
        layout.setSpacing(sp.GAP_XS)

        # Header with signal type and add button
        header_layout = QHBoxLayout()
        signal_label = QLabel(f"{self.signal}")
        signal_label.setStyleSheet(f"color:{signal_color}; font-weight:{ty.WEIGHT_BOLD};")
        header_layout.addWidget(signal_label)

        header_layout.addStretch()

        add_btn = QPushButton("➕ Add")
        add_btn.setFixedSize(60, 25)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.BLUE};
                color: {c.TEXT_INVERSE};
                border: none;
                border-radius: {sp.RADIUS_SM}px;
                font-size: {ty.SIZE_XS}pt;
            }}
            QPushButton:hover {{
                background: {c.BLUE}CC;
            }}
        """)
        add_btn.clicked.connect(self._on_add_clicked)
        header_layout.addWidget(add_btn)

        layout.addLayout(header_layout)

        # Example name
        name_label = QLabel(f"<b>{self.example_name}</b>")
        name_label.setStyleSheet(f"color:{c.TEXT_MAIN};")
        layout.addWidget(name_label)

        # Rules preview
        for rule in self.rules:
            rule_text = self._format_rule(rule)
            rule_label = QLabel(rule_text)
            rule_label.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            rule_label.setWordWrap(True)
            layout.addWidget(rule_label)

    def _format_rule(self, rule: dict) -> str:
        """Format a rule for display"""
        try:
            lhs = rule.get("lhs", {})
            rhs = rule.get("rhs", {})
            op = rule.get("op", "?")
            weight = rule.get("weight", 1.0)

            lhs_str = self._format_side(lhs)
            rhs_str = self._format_side(rhs)

            return f"  • {lhs_str} {op} {rhs_str} (w={weight:.1f})"
        except:
            return "  • Invalid rule"

    def _format_side(self, side: dict) -> str:
        """Format a side dictionary for display"""
        try:
            t = side.get("type", "unknown")
            if t == "scalar":
                return str(side.get("value", "?"))
            elif t == "column":
                col = side.get("column", "?")
                shift = side.get("shift", 0)
                return f"{col.upper()}" + (f"[{shift}]" if shift > 0 else "")
            else:  # indicator
                ind = side.get("indicator", "?").upper()
                params = side.get("params", {})
                shift = side.get("shift", 0)
                param_str = ",".join(f"{k}={v}" for k, v in params.items()) if params else ""
                return f"{ind}({param_str})" + (f"[{shift}]" if shift > 0 else "")
        except:
            return "?"

    def _on_add_clicked(self):
        """Handle add button click"""
        if hasattr(self.parent_tab, 'add_example'):
            self.parent_tab.add_example(self.example_name, self.signal, self.rules)


class _PresetCard(QFrame, ThemedMixin):
    """Card widget for displaying a preset"""

    def __init__(self, signal_type: str, preset_name: str, rules: list, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)
            self.signal_type = signal_type
            self.preset_name = preset_name
            self.rules = rules
            self.parent_tab = parent

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self._init_ui()
            self.apply_theme()

        except Exception as e:
            logger.error(f"[_PresetCard.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        self.signal_type = ""
        self.preset_name = ""
        self.rules = []
        self.parent_tab = None

    def apply_theme(self, _: str = None) -> None:
        """Apply theme colors to the card."""
        try:
            c = self._c
            sp = self._sp
            signal_meta = get_signal_meta()
            color = signal_meta.get(self.signal_type, ("", c.TEXT_DIM, ""))[1]

            self.setStyleSheet(f"""
                QFrame {{
                    background: {c.BG_PANEL};
                    border: {sp.SEPARATOR}px solid {c.BORDER};
                    border-radius: {sp.RADIUS_LG}px;
                    padding: {sp.PAD_LG}px;
                }}
                QFrame:hover {{
                    border: {sp.SEPARATOR}px solid {color};
                }}
            """)
        except Exception as e:
            logger.error(f"[_PresetCard.apply_theme] Failed: {e}", exc_info=True)

    def _init_ui(self):
        c = self._c
        sp = self._sp
        ty = self._ty
        signal_meta = get_signal_meta()
        color = signal_meta.get(self.signal_type, ("", c.TEXT_DIM, ""))[1]

        layout = QVBoxLayout(self)
        layout.setSpacing(sp.GAP_XS)

        # Header with preset name and apply button
        header_layout = QHBoxLayout()
        name_label = QLabel(f"<b>{self.preset_name}</b>")
        name_label.setStyleSheet(f"color:{color}; font-size:{ty.SIZE_MD}pt;")
        header_layout.addWidget(name_label)

        header_layout.addStretch()

        apply_btn = QPushButton("📋 Apply")
        apply_btn.setFixedSize(80, 30)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: {c.TEXT_INVERSE};
                border: none;
                border-radius: {sp.RADIUS_SM}px;
                font-weight: {ty.WEIGHT_BOLD};
                font-size: {ty.SIZE_XS}pt;
            }}
            QPushButton:hover {{
                background: {color}CC;
            }}
        """)
        apply_btn.clicked.connect(self._on_apply_clicked)
        header_layout.addWidget(apply_btn)

        layout.addLayout(header_layout)

        # Rules list
        for rule in self.rules:
            rule_text = self._format_rule(rule)
            rule_label = QLabel(rule_text)
            rule_label.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_XS}pt;")
            rule_label.setWordWrap(True)
            layout.addWidget(rule_label)

    def _format_rule(self, rule: dict) -> str:
        """Format a rule for display"""
        try:
            lhs = rule.get("lhs", {})
            rhs = rule.get("rhs", {})
            op = rule.get("op", "?")
            weight = rule.get("weight", 1.0)

            lhs_str = self._format_side(lhs)
            rhs_str = self._format_side(rhs)

            return f"  • {lhs_str} {op} {rhs_str} (w={weight:.1f})"
        except:
            return "  • Invalid rule"

    def _format_side(self, side: dict) -> str:
        """Format a side dictionary for display"""
        try:
            t = side.get("type", "unknown")
            if t == "scalar":
                return str(side.get("value", "?"))
            elif t == "column":
                col = side.get("column", "?")
                shift = side.get("shift", 0)
                return f"{col.upper()}" + (f"[{shift}]" if shift > 0 else "")
            else:  # indicator
                ind = side.get("indicator", "?").upper()
                params = side.get("params", {})
                shift = side.get("shift", 0)
                param_str = ",".join(f"{k}={v}" for k, v in params.items()) if params else ""
                return f"{ind}({param_str})" + (f"[{shift}]" if shift > 0 else "")
        except:
            return "?"

    def _on_apply_clicked(self):
        """Handle apply button click"""
        if hasattr(self.parent_tab, 'apply_preset'):
            self.parent_tab.apply_preset(self.signal_type, self.preset_name, self.rules)


class StrategyHelpTab(QWidget, ThemedMixin):
    """
    Comprehensive help and documentation tab with interactive examples.
    Separated from main editor for better maintainability.
    FULLY INTEGRATED with ThemeManager for dynamic theming.
    """

    def __init__(self, parent=None):
        self._safe_defaults_init()
        try:
            super().__init__(parent)

            # Rule 13.2: Connect to theme and density signals
            theme_manager.theme_changed.connect(self.apply_theme)
            theme_manager.density_changed.connect(self.apply_theme)

            self.parent_window = parent
            self.pages = {}
            self.nav_tree = None
            self.content_stack = None
            self.search_box = None

            self._init_ui()
            self._connect_navigation()
            self.show_page("welcome")

            self.apply_theme()

            logger.info("StrategyHelpTab initialized")

        except Exception as e:
            logger.critical(f"[StrategyHelpTab.__init__] Failed: {e}", exc_info=True)
            super().__init__(parent)

    def _safe_defaults_init(self):
        """Rule 2: Initialize all attributes with safe defaults"""
        self.parent_window = None
        self.pages = {}
        self.nav_tree = None
        self.content_stack = None
        self.search_box = None

    def apply_theme(self, _: str = None) -> None:
        """
        Rule 13.2: Apply theme colors to the help tab.
        Called on theme change, density change, and initial render.
        """
        try:
            c = self._c
            sp = self._sp
            ty = self._ty

            # Update splitter
            splitter = self.findChild(QSplitter)
            if splitter:
                splitter.setStyleSheet(f"""
                    QSplitter::handle {{
                        background: {c.BORDER};
                    }}
                """)

            # Update content stack
            if self.content_stack:
                self.content_stack.setStyleSheet(f"""
                    QStackedWidget {{
                        background: {c.BG_PANEL};
                        border-left: {sp.SEPARATOR}px solid {c.BORDER};
                    }}
                """)

            # Update navigation panel
            nav_widget = self.findChild(QWidget, "nav_panel")
            if nav_widget:
                nav_widget.setStyleSheet(f"background: {c.BG_PANEL};")

            # Update header
            header = self.findChild(QLabel, "header")
            if header:
                header.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_BODY}pt; font-weight:{ty.WEIGHT_BOLD}; padding:{sp.PAD_MD}px;")

            # Update search icon
            search_icon = self.findChild(QLabel, "search_icon")
            if search_icon:
                search_icon.setStyleSheet(f"color:{c.TEXT_DIM};")

            # Update navigation tree
            if self.nav_tree:
                self.nav_tree.setStyleSheet(f"""
                    QTreeWidget {{
                        background: {c.BG_HOVER};
                        border: {sp.SEPARATOR}px solid {c.BORDER};
                        border-radius: {sp.RADIUS_SM}px;
                    }}
                    QTreeWidget::item {{
                        padding: {sp.PAD_SM}px;
                        border-bottom: {sp.SEPARATOR}px solid {c.BORDER}40;
                    }}
                    QTreeWidget::item:selected {{
                        background: {c.BG_SELECTED};
                        color: {c.BLUE};
                    }}
                """)

            # Update quick links
            quick_links = self.findChild(QFrame, "quick_links")
            if quick_links:
                quick_links.setStyleSheet(f"border-top: {sp.SEPARATOR}px solid {c.BORDER}; margin-top: {sp.PAD_MD}px;")

            logger.debug("[StrategyHelpTab.apply_theme] Applied theme")
        except Exception as e:
            logger.error(f"[StrategyHelpTab.apply_theme] Failed: {e}", exc_info=True)

    def _init_ui(self):
        """Initialize the UI"""
        sp = self._sp

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(sp.SPLITTER)

        # Left navigation panel
        nav_widget = self._create_navigation_panel()
        splitter.addWidget(nav_widget)

        # Right content panel (stacked)
        self.content_stack = QStackedWidget()

        # Create all content pages
        self._create_all_pages()

        splitter.addWidget(self.content_stack)
        splitter.setSizes([250, 750])  # 25% navigation, 75% content (design requirement)

        main_layout.addWidget(splitter)

    def _create_navigation_panel(self) -> QWidget:
        """Create the left navigation tree"""
        sp = self._sp
        c = self._c
        ty = self._ty

        widget = QWidget()
        widget.setObjectName("nav_panel")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(sp.PAD_MD, sp.PAD_MD, sp.PAD_MD, sp.PAD_MD)

        # Header
        header = QLabel("📚 HELP & DOCUMENTATION")
        header.setObjectName("header")
        layout.addWidget(header)

        # Search box
        search_layout = QHBoxLayout()
        search_icon = QLabel("🔍")
        search_icon.setObjectName("search_icon")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search help...")
        self.search_box.textChanged.connect(self._filter_navigation)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)

        # Navigation tree
        self.nav_tree = QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setIndentation(sp.PAD_LG)

        self._populate_navigation()
        layout.addWidget(self.nav_tree)

        # Quick links at bottom (fixed URLs)
        quick_links = QFrame()
        quick_links.setObjectName("quick_links")
        links_layout = QVBoxLayout(quick_links)

        # Use placeholder URLs or hide if not available
        online_docs = QPushButton("🌐 Online Documentation")
        online_docs.clicked.connect(lambda: QMessageBox.information(
            self, "Coming Soon", "Online documentation will be available in a future update."))
        links_layout.addWidget(online_docs)

        video_tutorials = QPushButton("🎥 Video Tutorials")
        video_tutorials.clicked.connect(lambda: QMessageBox.information(
            self, "Coming Soon", "Video tutorials will be available in a future update."))
        links_layout.addWidget(video_tutorials)

        report_issue = QPushButton("🐛 Report Issue")
        report_issue.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/yourusername/TradingGUI/issues/new")))
        links_layout.addWidget(report_issue)

        layout.addWidget(quick_links)

        return widget

    def _populate_navigation(self):
        """Populate the navigation tree with help topics"""
        # Welcome/Getting Started
        welcome = QTreeWidgetItem(["🏠 Welcome & Getting Started"])
        welcome.addChild(QTreeWidgetItem(["📋 Overview"]))
        welcome.addChild(QTreeWidgetItem(["🚀 Quick Start Guide"]))
        welcome.addChild(QTreeWidgetItem(["⚙️ First-Time Setup"]))
        self.nav_tree.addTopLevelItem(welcome)

        # Interface Guide
        interface = QTreeWidgetItem(["🖥️ Interface Guide"])
        interface.addChild(QTreeWidgetItem(["📊 Strategy List Panel"]))
        interface.addChild(QTreeWidgetItem(["⚙ Info Tab"]))
        interface.addChild(QTreeWidgetItem(["📊 Indicators Tab"]))
        interface.addChild(QTreeWidgetItem(["🔬 Signal Rules Tab"]))
        interface.addChild(QTreeWidgetItem(["📚 Help Tab"]))
        interface.addChild(QTreeWidgetItem(["📦 Import/Export"]))
        self.nav_tree.addTopLevelItem(interface)

        # Signal Groups
        signals = QTreeWidgetItem(["🔴 Signal Groups"])
        signals.addChild(QTreeWidgetItem(["📈 BUY CALL - Bullish Entries"]))
        signals.addChild(QTreeWidgetItem(["📉 BUY PUT - Bearish Entries"]))
        signals.addChild(QTreeWidgetItem(["🔴 EXIT CALL - Exit Long"]))
        signals.addChild(QTreeWidgetItem(["🟠 EXIT PUT - Exit Short"]))
        signals.addChild(QTreeWidgetItem(["⏸ HOLD - No Action"]))
        signals.addChild(QTreeWidgetItem(["⚖️ Conflict Resolution"]))
        self.nav_tree.addTopLevelItem(signals)

        # Building Rules
        rules = QTreeWidgetItem(["🔨 Building Rules"])
        rules.addChild(QTreeWidgetItem(["📐 Rule Structure"]))
        rules.addChild(QTreeWidgetItem(["🔹 Left Side Options"]))
        rules.addChild(QTreeWidgetItem(["🔸 Right Side Options"]))
        rules.addChild(QTreeWidgetItem(["⚖️ Operators"]))
        rules.addChild(QTreeWidgetItem(["⏱️ Shift Controls"]))
        rules.addChild(QTreeWidgetItem(["📝 Step-by-Step Guide"]))
        rules.addChild(QTreeWidgetItem(["💡 Example Rules"]))
        self.nav_tree.addTopLevelItem(rules)

        # Indicators
        indicators = QTreeWidgetItem(["📊 Indicators"])
        indicators.addChild(QTreeWidgetItem(["⚡ Momentum Indicators"]))
        indicators.addChild(QTreeWidgetItem(["📈 Trend Indicators"]))
        indicators.addChild(QTreeWidgetItem(["📉 Volatility Indicators"]))
        indicators.addChild(QTreeWidgetItem(["📊 Volume Indicators"]))
        indicators.addChild(QTreeWidgetItem(["📐 Derived Columns"]))
        indicators.addChild(QTreeWidgetItem(["⚙️ Parameter Settings"]))
        self.nav_tree.addTopLevelItem(indicators)

        # Confidence Scoring
        confidence = QTreeWidgetItem(["🎯 Confidence Scoring"])
        confidence.addChild(QTreeWidgetItem(["⚖️ Rule Weights"]))
        confidence.addChild(QTreeWidgetItem(["📊 How Confidence is Calculated"]))
        confidence.addChild(QTreeWidgetItem(["🎚️ Setting Thresholds"]))
        confidence.addChild(QTreeWidgetItem(["📈 Interpreting Confidence"]))
        confidence.addChild(QTreeWidgetItem(["💡 Weight Best Practices"]))
        self.nav_tree.addTopLevelItem(confidence)

        # Strategy Management
        management = QTreeWidgetItem(["📋 Strategy Management"])
        management.addChild(QTreeWidgetItem(["➕ Creating Strategies"]))
        management.addChild(QTreeWidgetItem(["⧉ Duplicating"]))
        management.addChild(QTreeWidgetItem(["⚡ Activating"]))
        management.addChild(QTreeWidgetItem(["🗑️ Deleting"]))
        management.addChild(QTreeWidgetItem(["📦 Import/Export"]))
        self.nav_tree.addTopLevelItem(management)

        # Presets
        presets = QTreeWidgetItem(["📋 Presets"])
        presets.addChild(QTreeWidgetItem(["📈 BUY CALL Presets"]))
        presets.addChild(QTreeWidgetItem(["📉 BUY PUT Presets"]))
        presets.addChild(QTreeWidgetItem(["🔴 EXIT CALL Presets"]))
        presets.addChild(QTreeWidgetItem(["🟠 EXIT PUT Presets"]))
        presets.addChild(QTreeWidgetItem(["⏸ HOLD Presets"]))
        self.nav_tree.addTopLevelItem(presets)

        # Best Practices
        best_practices = QTreeWidgetItem(["✨ Best Practices"])
        best_practices.addChild(QTreeWidgetItem(["🎯 Strategy Design"]))
        best_practices.addChild(QTreeWidgetItem(["⚖️ Weight Selection"]))
        best_practices.addChild(QTreeWidgetItem(["📊 Indicator Combinations"]))
        best_practices.addChild(QTreeWidgetItem(["🎚️ Threshold Settings"]))
        best_practices.addChild(QTreeWidgetItem(["⚠️ Common Mistakes"]))
        self.nav_tree.addTopLevelItem(best_practices)

        # Troubleshooting
        troubleshooting = QTreeWidgetItem(["🔧 Troubleshooting"])
        troubleshooting.addChild(QTreeWidgetItem(["❌ Common Errors"]))
        troubleshooting.addChild(QTreeWidgetItem(["🔍 Debugging Tips"]))
        troubleshooting.addChild(QTreeWidgetItem(["📊 Log Analysis"]))
        troubleshooting.addChild(QTreeWidgetItem(["❓ FAQ"]))
        self.nav_tree.addTopLevelItem(troubleshooting)

        # Keyboard Shortcuts
        shortcuts = QTreeWidgetItem(["⌨️ Keyboard Shortcuts"])
        self.nav_tree.addTopLevelItem(shortcuts)

        # Version History
        version = QTreeWidgetItem(["📝 Version History"])
        self.nav_tree.addTopLevelItem(version)

        # Expand all top-level items
        for i in range(self.nav_tree.topLevelItemCount()):
            self.nav_tree.topLevelItem(i).setExpanded(True)

    def _create_all_pages(self):
        """Create all content pages for the help system"""
        # Welcome Page
        self.pages["welcome"] = self._create_welcome_page()
        self.content_stack.addWidget(self.pages["welcome"])

        # Overview
        self.pages["📋 Overview"] = self._create_text_page(
            "📋 Overview",
            self._get_overview_content()
        )
        self.content_stack.addWidget(self.pages["📋 Overview"])

        # Quick Start Guide
        self.pages["🚀 Quick Start Guide"] = self._create_quick_start_page()
        self.content_stack.addWidget(self.pages["🚀 Quick Start Guide"])

        # Rule Structure
        self.pages["📐 Rule Structure"] = self._create_rule_structure_page()
        self.content_stack.addWidget(self.pages["📐 Rule Structure"])

        # Operators
        self.pages["⚖️ Operators"] = self._create_operators_page()
        self.content_stack.addWidget(self.pages["⚖️ Operators"])

        # Shift Controls
        self.pages["⏱️ Shift Controls"] = self._create_shift_controls_page()
        self.content_stack.addWidget(self.pages["⏱️ Shift Controls"])

        # Example Rules
        self.pages["💡 Example Rules"] = self._create_examples_page()
        self.content_stack.addWidget(self.pages["💡 Example Rules"])

        # Confidence Scoring
        self.pages["⚖️ Rule Weights"] = self._create_weights_page()
        self.content_stack.addWidget(self.pages["⚖️ Rule Weights"])

        self.pages["📊 How Confidence is Calculated"] = self._create_confidence_calculation_page()
        self.content_stack.addWidget(self.pages["📊 How Confidence is Calculated"])

        self.pages["🎚️ Setting Thresholds"] = self._create_thresholds_page()
        self.content_stack.addWidget(self.pages["🎚️ Setting Thresholds"])

        # Strategy Management
        self.pages["➕ Creating Strategies"] = self._create_text_page(
            "➕ Creating Strategies",
            self._get_creating_strategies_content()
        )
        self.content_stack.addWidget(self.pages["➕ Creating Strategies"])

        self.pages["⚡ Activating"] = self._create_text_page(
            "⚡ Activating",
            self._get_activating_content()
        )
        self.content_stack.addWidget(self.pages["⚡ Activating"])

        # Presets Pages
        self.pages["📈 BUY CALL Presets"] = self._create_presets_page("BUY_CALL")
        self.content_stack.addWidget(self.pages["📈 BUY CALL Presets"])

        self.pages["📉 BUY PUT Presets"] = self._create_presets_page("BUY_PUT")
        self.content_stack.addWidget(self.pages["📉 BUY PUT Presets"])

        self.pages["🔴 EXIT CALL Presets"] = self._create_presets_page("EXIT_CALL")
        self.content_stack.addWidget(self.pages["🔴 EXIT CALL Presets"])

        self.pages["🟠 EXIT PUT Presets"] = self._create_presets_page("EXIT_PUT")
        self.content_stack.addWidget(self.pages["🟠 EXIT PUT Presets"])

        self.pages["⏸ HOLD Presets"] = self._create_presets_page("HOLD")
        self.content_stack.addWidget(self.pages["⏸ HOLD Presets"])

        # Keyboard Shortcuts
        self.pages["⌨️ Keyboard Shortcuts"] = self._create_shortcuts_page()
        self.content_stack.addWidget(self.pages["⌨️ Keyboard Shortcuts"])

        # FAQ
        self.pages["❓ FAQ"] = self._create_faq_page()
        self.content_stack.addWidget(self.pages["❓ FAQ"])

        # Common Errors
        self.pages["❌ Common Errors"] = self._create_errors_page()
        self.content_stack.addWidget(self.pages["❌ Common Errors"])

        # Best Practices
        self.pages["🎯 Strategy Design"] = self._create_best_practices_page()
        self.content_stack.addWidget(self.pages["🎯 Strategy Design"])

    def _create_welcome_page(self) -> QWidget:
        """Create the welcome page with quick actions"""
        c = self._c
        sp = self._sp
        ty = self._ty
        signal_meta = get_signal_meta()

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)
        layout.setSpacing(sp.PAD_XL)

        # Welcome header
        header = QLabel("🚀 Welcome to the Strategy Editor!")
        header.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_XL}pt; font-weight:{ty.WEIGHT_BOLD};")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Subtitle
        subtitle = QLabel("Your complete toolkit for creating and managing trading strategies")
        subtitle.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_BODY}pt;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Quick action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(sp.PAD_XL)

        new_btn = QPushButton("➕ New Strategy")
        new_btn.setFixedSize(200, 60)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.GREEN};
                color: {c.TEXT_INVERSE};
                border: none;
                border-radius: {sp.RADIUS_MD}px;
                font-size: {ty.SIZE_BODY}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background: {c.GREEN_BRIGHT};
            }}
        """)
        new_btn.clicked.connect(self._quick_action_new)
        actions_layout.addWidget(new_btn)

        import_btn = QPushButton("📥 Import Strategy")
        import_btn.setFixedSize(200, 60)
        import_btn.setStyleSheet(f"""
            QPushButton {{
                background: {c.BLUE_DARK};
                color: {c.TEXT_INVERSE};
                border: none;
                border-radius: {sp.RADIUS_MD}px;
                font-size: {ty.SIZE_BODY}pt;
                font-weight: {ty.WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background: {c.BLUE};
            }}
        """)
        import_btn.clicked.connect(self._quick_action_import)
        actions_layout.addWidget(import_btn)

        layout.addLayout(actions_layout)

        # Quick stats
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"background:{c.BG_HOVER}; border-radius:{sp.RADIUS_LG}px; padding:{sp.PAD_XL}px;")
        stats_layout = QHBoxLayout(stats_frame)

        # Total strategies
        total_strategies = QLabel(f"📊 {strategy_manager.count()}")
        total_strategies.setStyleSheet(f"color:{c.GREEN}; font-size:{ty.SIZE_LG}pt; font-weight:{ty.WEIGHT_BOLD};")
        total_strategies.setAlignment(Qt.AlignCenter)
        stats_layout.addWidget(total_strategies)

        # Active strategy
        active_name = strategy_manager.get_active_name()
        active = QLabel(f"⚡ {active_name}")
        active.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_LG}pt; font-weight:{ty.WEIGHT_BOLD};")
        active.setAlignment(Qt.AlignCenter)
        stats_layout.addWidget(active)

        # Total presets
        total_presets = sum(len(get_preset_names(sig)) for sig in signal_meta.keys())
        presets = QLabel(f"📋 {total_presets} Presets")
        presets.setStyleSheet(f"color:{c.PURPLE}; font-size:{ty.SIZE_LG}pt; font-weight:{ty.WEIGHT_BOLD};")
        presets.setAlignment(Qt.AlignCenter)
        stats_layout.addWidget(presets)

        layout.addWidget(stats_frame)

        # Getting started guide
        guide = QTextEdit()
        guide.setReadOnly(True)
        guide.setStyleSheet(f"""
            QTextEdit {{
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                padding: {sp.PAD_LG}px;
                font-size: {ty.SIZE_BODY}pt;
            }}
        """)
        guide.setHtml(self._get_welcome_guide_content())
        layout.addWidget(guide, 1)

        return widget

    def _create_quick_start_page(self) -> QWidget:
        """Create the quick start guide page"""
        return self._create_text_page("🚀 Quick Start Guide", self._get_quick_start_content())

    def _create_rule_structure_page(self) -> QWidget:
        """Create the rule structure explanation page"""
        return self._create_text_page("📐 Rule Structure", self._get_rule_structure_content())

    def _create_operators_page(self) -> QWidget:
        """Create the operators explanation page"""
        return self._create_text_page("⚖️ Operators", self._get_operators_content())

    def _create_shift_controls_page(self) -> QWidget:
        """Create the shift controls explanation page"""
        return self._create_text_page("⏱️ Shift Controls", self._get_shift_controls_content())

    def _create_examples_page(self) -> QWidget:
        """Create the examples page with interactive rule templates"""
        c = self._c
        sp = self._sp
        ty = self._ty
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)

        # Title
        title = QLabel("💡 Example Rules")
        title.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_XL}pt; font-weight:{ty.WEIGHT_BOLD};")
        layout.addWidget(title)

        # Create tabs for different example categories
        tabs = self._create_example_tabs()
        layout.addWidget(tabs)

        return widget

    def _create_example_tabs(self):
        """Create tabs for different example categories"""
        from PyQt5.QtWidgets import QTabWidget, QScrollArea

        c = self._c
        sp = self._sp

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_SM}px;
            }}
        """)

        # Define examples
        examples_by_category = {
            "Momentum": [
                ("RSI Oversold Bounce", "BUY_CALL", [
                    {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                     "op": "<", "rhs": {"type": "scalar", "value": 30}, "weight": 1.5},
                ]),
                ("RSI Overbought Reversal", "BUY_PUT", [
                    {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                     "op": ">", "rhs": {"type": "scalar", "value": 70}, "weight": 1.5},

                ]),
                ("MACD Bullish Crossover", "BUY_CALL", [

                    {"lhs": {"type": "indicator", "indicator": "macd", "params": {"column": "histogram"}},
                     "op": ">", "rhs": {"type": "scalar", "value": 0}, "weight": 1.5}
                ]),
            ],
            "Trend": [
                ("Golden Cross", "BUY_CALL", [

                    {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}},
                     "op": ">", "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 50}},
                     "weight": 1.8}
                ]),
                ("Death Cross", "BUY_PUT", [

                    {"lhs": {"type": "indicator", "indicator": "ema", "params": {"length": 21}},
                     "op": "<", "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 50}},
                     "weight": 1.8}
                ]),
                ("ADX Strong Trend", "HOLD", [
                    {"lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}},
                     "op": ">", "rhs": {"type": "scalar", "value": 25}, "weight": 2.0},
                    {"lhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}},
                     "op": ">", "rhs": {"type": "indicator", "indicator": "adx", "params": {"length": 14}, "shift": 1},
                     "weight": 1.5}
                ]),
            ],
            "Volatility": [
                ("Bollinger Band Bounce", "BUY_CALL", [
                    {"lhs": {"type": "column", "column": "close"},
                     "op": "<", "rhs": {"type": "indicator", "indicator": "bbands",
                                        "params": {"length": 20, "std": 2, "column": "lower"}}, "weight": 1.5},
                ]),
                ("Bollinger Band Top Rejection", "BUY_PUT", [
                    {"lhs": {"type": "column", "column": "close"},
                     "op": ">", "rhs": {"type": "indicator", "indicator": "bbands",
                                        "params": {"length": 20, "std": 2, "column": "upper"}}, "weight": 1.8},
                    {"lhs": {"type": "indicator", "indicator": "rsi", "params": {"length": 14}},
                     "op": ">", "rhs": {"type": "scalar", "value": 70}, "weight": 2.0}
                ]),
            ],
            "Volume": [
                ("Volume Spike", "BUY_CALL", [
                    {"lhs": {"type": "column", "column": "volume"},
                     "op": ">", "rhs": {"type": "derived", "expression": "volume_sma(20) * 1.5"}, "weight": 1.8},
                    {"lhs": {"type": "column", "column": "close"},
                     "op": ">", "rhs": {"type": "column", "column": "open"}, "weight": 1.5},
                ]),
                ("OBV Breakout", "BUY_CALL", [
                    {"lhs": {"type": "column", "column": "close"},
                     "op": ">", "rhs": {"type": "indicator", "indicator": "ema", "params": {"length": 9}},
                     "weight": 1.3}
                ]),
            ],
        }

        for category, examples in examples_by_category.items():
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setSpacing(sp.GAP_MD)

            for example_name, signal, rules in examples:
                card = _ExampleCard(example_name, signal, rules, self)
                container_layout.addWidget(card)

            container_layout.addStretch()
            scroll.setWidget(container)
            tabs.addTab(scroll, category)

        return tabs

    def _create_weights_page(self) -> QWidget:
        """Create the rule weights explanation page"""
        return self._create_text_page("⚖️ Rule Weights", self._get_weights_content())

    def _create_confidence_calculation_page(self) -> QWidget:
        """Create the confidence calculation explanation page"""
        return self._create_text_page("📊 Confidence Calculation", self._get_confidence_calculation_content())

    def _create_thresholds_page(self) -> QWidget:
        """Create the confidence thresholds explanation page"""
        return self._create_text_page("🎚️ Setting Thresholds", self._get_thresholds_content())

    def _create_presets_page(self, signal_type: str) -> QWidget:
        """Create a page showing all presets for a signal type"""
        c = self._c
        sp = self._sp
        ty = self._ty
        signal_meta = get_signal_meta()
        emoji, color, label = signal_meta.get(signal_type, ("", c.TEXT_DIM, signal_type))

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)

        # Header
        header = QLabel(f"{emoji} {label} Presets")
        header.setStyleSheet(f"color:{color}; font-size:{ty.SIZE_LG}pt; font-weight:{ty.WEIGHT_BOLD};")
        layout.addWidget(header)

        # Description
        desc = QLabel(f"Pre-built {signal_type} strategies. Click 'Apply' to add to current strategy.")
        desc.setStyleSheet(f"color:{c.TEXT_DIM}; font-size:{ty.SIZE_BODY}pt;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Scroll area for presets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(sp.GAP_LG)

        # Get all presets for this signal type
        presets = get_preset_names(signal_type)
        for preset_name in presets:
            rules = get_preset_rules(signal_type, preset_name)
            if rules:
                card = _PresetCard(signal_type, preset_name, rules, self)
                container_layout.addWidget(card)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        return widget

    def _create_shortcuts_page(self) -> QWidget:
        """Create the keyboard shortcuts page"""
        return self._create_text_page("⌨️ Keyboard Shortcuts", self._get_shortcuts_content())

    def _create_faq_page(self) -> QWidget:
        """Create the FAQ page"""
        return self._create_text_page("❓ FAQ", self._get_faq_content())

    def _create_errors_page(self) -> QWidget:
        """Create the common errors page"""
        return self._create_text_page("❌ Common Errors", self._get_errors_content())

    def _create_best_practices_page(self) -> QWidget:
        """Create the best practices page"""
        return self._create_text_page("✨ Best Practices", self._get_best_practices_content())

    def _create_text_page(self, title: str, content: str) -> QWidget:
        """Create a simple text page with themed styling"""
        c = self._c
        sp = self._sp
        ty = self._ty

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(sp.PAD_XL, sp.PAD_XL, sp.PAD_XL, sp.PAD_XL)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color:{c.BLUE}; font-size:{ty.SIZE_LG}pt; font-weight:{ty.WEIGHT_BOLD};")
        layout.addWidget(title_lbl)

        # Content
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(f"""
            QTextEdit {{
                background: {c.BG_HOVER};
                border: {sp.SEPARATOR}px solid {c.BORDER};
                border-radius: {sp.RADIUS_LG}px;
                padding: {sp.PAD_XL}px;
                font-size: {ty.SIZE_BODY}pt;
                line-height: {ty.LINE_HEIGHT_NORMAL};
            }}
        """)
        text.setHtml(content)
        layout.addWidget(text, 1)

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
            self.content_stack.setCurrentWidget(self.pages.get("welcome",
                                                               self.pages.get("📋 Overview")))

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

    def _quick_action_new(self):
        """Handle new strategy quick action"""
        if hasattr(self.parent_window, "_list_panel"):
            self.parent_window._list_panel._on_new()

    def _quick_action_import(self):
        """Handle import quick action"""
        if hasattr(self.parent_window, "_on_import"):
            self.parent_window._on_import()

    def apply_preset(self, signal: str, preset_name: str, rules: list):
        """Apply a preset to the current strategy"""
        try:
            if hasattr(self.parent_window, "_rules_tab"):
                rules_tab = self.parent_window._rules_tab
                if signal in rules_tab._panels:
                    panel = rules_tab._panels[signal]
                    for rule in rules:
                        panel._add_rule(rule)

                    QMessageBox.information(self, "Preset Applied",
                                            f"Added {len(rules)} rules from '{preset_name}' to {signal}")
        except Exception as e:
            logger.error(f"Failed to apply preset: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to apply preset: {e}")

    def add_example(self, example_name: str, signal: str, rules: list):
        """Add an example rule to the current strategy"""
        try:
            if hasattr(self.parent_window, "_rules_tab"):
                rules_tab = self.parent_window._rules_tab
                if signal in rules_tab._panels:
                    panel = rules_tab._panels[signal]
                    for rule in rules:
                        panel._add_rule(rule)

                    QMessageBox.information(self, "Example Added",
                                            f"Added example '{example_name}' to {signal}")
        except Exception as e:
            logger.error(f"Failed to add example: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to add example: {e}")

    # Content generation methods
    def _get_overview_content(self) -> str:
        c = self._c
        return f"""
        <h2 style='color:{c.BLUE}'>Strategy Editor Overview</h2>
        <p>The Strategy Editor is a powerful tool for creating, managing, and testing trading strategies based on technical indicators.</p>

        <h3 style='color:{c.GREEN}'>Key Features:</h3>
        <ul>
            <li><b>Rule-based system</b> - Create complex trading conditions using indicators, price data, and constants</li>
            <li><b>5 Signal Groups</b> - BUY_CALL, BUY_PUT, EXIT_CALL, EXIT_PUT, HOLD</li>
            <li><b>80+ Technical Indicators</b> - RSI, MACD, Bollinger Bands, and more</li>
            <li><b>Confidence Scoring</b> - Weighted rules with minimum confidence thresholds</li>
            <li><b>Presets</b> - 100+ pre-built strategies to get started quickly</li>
            <li><b>Import/Export</b> - Share strategies via JSON</li>
        </ul>

        <h3 style='color:{c.GREEN}'>Architecture</h3>
        <p>The editor uses a database-backed strategy manager that stores all strategies in SQLite. Each strategy contains:</p>
        <ul>
            <li>Name and description</li>
            <li>Engine configuration with rules for each signal group</li>
            <li>Confidence threshold settings</li>
            <li>Creation and update timestamps</li>
        </ul>
        """

    def _get_welcome_guide_content(self) -> str:
        c = self._c
        return f"""
        <h2 style='color:{c.BLUE}'>📋 Getting Started in 3 Steps</h2>
        <table width="100%">
            <tr>
                <td width="33%" align="center" style="padding: {self._sp.PAD_MD}px;">
                    <h3 style='color:{c.GREEN}'>1️⃣ Create</h3>
                    <p>Click 'New Strategy' and give it a name</p>
                </td>
                <td width="33%" align="center" style="padding: {self._sp.PAD_MD}px;">
                    <h3 style='color:{c.GREEN}'>2️⃣ Configure</h3>
                    <p>Add rules using indicators and price data</p>
                </td>
                <td width="33%" align="center" style="padding: {self._sp.PAD_MD}px;">
                    <h3 style='color:{c.GREEN}'>3️⃣ Activate</h3>
                    <p>Click 'Activate' to start using it</p>
                </td>
            </tr>
        </table>

        <h3 style='color:{c.YELLOW}'>💡 Pro Tip</h3>
        <p>Start with a preset! Go to any signal group tab and click 'Load Preset' to see working examples.</p>

        <h3 style='color:{c.BLUE}'>🔍 Need Help?</h3>
        <p>Use the navigation tree on the left to explore detailed documentation on every feature.</p>
        """

    def _get_quick_start_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>🚀 Quick Start Guide</h1>

        <h2 style='color:{c.GREEN}'>5 Minutes to Your First Strategy</h2>

        <h3 style='color:{c.BLUE}'>Step 1: Create a Strategy</h3>
        <ol>
            <li>Click <b>"＋ New"</b> in the left panel</li>
            <li>Enter "My First Strategy" as the name</li>
            <li>The strategy appears in the list - it's automatically selected</li>
        </ol>

        <h3 style='color:{c.BLUE}'>Step 2: Add Basic Information</h3>
        <ol>
            <li>Go to the <b>⚙ Info</b> tab</li>
            <li>Add a description: "Simple RSI and EMA strategy"</li>
            <li>Notice the statistics show 0 rules - we'll fix that</li>
        </ol>

        <h3 style='color:{c.BLUE}'>Step 3: Create Your First Rule</h3>
        <ol>
            <li>Go to the <b>🔬 Signal Rules</b> tab</li>
            <li>Click the <b>📈 BUY CALL</b> tab</li>
            <li>Click <b>"＋ Add Rule"</b></li>
            <li>Configure the rule:
                <ul>
                    <li>Left side: <b>indicator</b> → select <b>RSI</b> (shift: 0)</li>
                    <li>Operator: <b><</b> (less than)</li>
                    <li>Right side: <b>scalar</b> → enter <b>30</b></li>
                    <li>Weight: <b>1.5</b></li>
                </ul>
            </li>
        </ol>

        <h3 style='color:{c.BLUE}'>Step 4: Add a Second Rule</h3>
        <ol>
            <li>Click <b>"＋ Add Rule"</b> again</li>
            <li>Configure:
                <ul>
                    <li>Left side: <b>indicator</b> → <b>EMA(9)</b></li>
                    <li>Operator: <b>></b></li>
                    <li>Right side: <b>indicator</b> → <b>EMA(21)</b></li>
                    <li>Weight: <b>2.0</b></li>
                </ul>
            </li>
        </ol>

        <h3 style='color:{c.BLUE}'>Step 5: Set Logic and Save</h3>
        <ol>
            <li>Set the logic dropdown to <b>"AND"</b> (both rules must be true)</li>
            <li>Click <b>"💾 Save"</b> in the footer</li>
            <li>Notice the rule count badge shows "2 rules"</li>
        </ol>

        <h3 style='color:{c.BLUE}'>Step 6: Activate Your Strategy</h3>
        <ol>
            <li>Click <b>"⚡ Activate This Strategy"</b> in the footer</li>
            <li>The strategy is now active and will generate signals</li>
            <li>Check the Strategy Picker sidebar to see confidence scores</li>
        </ol>

        <h3 style='color:{c.GREEN}'>✅ You're Done!</h3>
        <p>Your first strategy is now running. The engine will generate BUY_CALL signals when:</p>
        <ul>
            <li>RSI(14) is below 30 (oversold condition)</li>
            <li>AND the 9 EMA is above the 21 EMA (uptrend confirmation)</li>
        </ul>
        """

    def _get_rule_structure_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>📐 Rule Structure</h1>

        <p>Each rule in the Strategy Editor follows a simple but powerful structure:</p>

        <div style='background:{c.BG_HOVER}; padding:{self._sp.PAD_XL}px; border-radius:{self._sp.RADIUS_LG}px; margin:{self._sp.PAD_XL}px 0; text-align:center;'>
            <h2 style='color:{c.BLUE};'>[LEFT SIDE] [OPERATOR] [RIGHT SIDE] [WEIGHT]</h2>
        </div>

        <h2 style='color:{c.BLUE}'>🔹 Left Side (Condition)</h2>
        <p>The left side defines what you're evaluating. Options:</p>

        <h3 style='color:{c.GREEN}'>📊 Indicator</h3>
        <p>Technical indicators like RSI, MACD, Bollinger Bands, etc.</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Example: RSI(14) with shift: 0</pre>

        <h3 style='color:{c.GREEN}'>📈 Column</h3>
        <p>Price data columns: close, open, high, low, volume, or derived columns (hl2, hlc3, ohlc4)</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Example: close with shift: 1 (previous bar's close)</pre>

        <h3 style='color:{c.GREEN}'>#️⃣ Scalar</h3>
        <p>Constant numeric values</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Example: 30, 70, 100.5</pre>

        <h2 style='color:{c.BLUE}'>⚖️ Operator</h2>
        <p>How the left and right sides are compared:</p>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'>
                <th>Operator</th>
                <th>Description</th>
                <th>Example</th>
            </tr>
            <tr><td><code>></code></td><td>Greater than</td><td>RSI > 70</td></tr>
            <tr><td><code><</code></td><td>Less than</td><td>RSI < 30</td></tr>
            <tr><td><code>>=</code></td><td>Greater than or equal</td><td>Close >= Open</td></tr>
            <tr><td><code><=</code></td><td>Less than or equal</td><td>Volume <= 1000</td></tr>
            <tr><td><code>==</code></td><td>Equal</td><td>Close == Open</td></tr>
            <tr><td><code>!=</code></td><td>Not equal</td><td>Close != Open</td></tr>
            <tr><td><code>between</code></td><td>Value between two thresholds</td><td>RSI between 30 and 70</td></tr>
        </table>

        <h2 style='color:{c.BLUE}'>🔸 Right Side (Target)</h2>
        <p>Same options as Left Side: Indicator, Column, or Scalar. This is what you're comparing against.</p>

        <h2 style='color:{c.BLUE}'>⚖️ Weight</h2>
        <p>A number from 0.1 to 5.0 indicating the importance of this rule in confidence scoring.</p>
        <ul>
            <li><b>Higher weight</b> = More important in the final confidence calculation</li>
            <li><b>Lower weight</b> = Less important, supporting condition</li>
            <li><b>Default:</b> 1.0</li>
        </ul>

        <h2 style='color:{c.BLUE}'>⏱️ Shift Control</h2>
        <p>Available for Indicators and Columns (not Scalars). Determines how many bars to look back:</p>
        <ul>
            <li><b>shift: 0</b> - Current bar (default)</li>
            <li><b>shift: 1</b> - Previous bar</li>
            <li><b>shift: n</b> - n bars ago</li>
        </ul>
        """

    def _get_operators_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>⚖️ Operators Explained</h1>

        <h2 style='color:{c.GREEN}'>Comparison Operators</h2>

        <h3 style='color:{c.BLUE}'>> (Greater Than)</h3>
        <p>TRUE if left side value is greater than right side value.</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
RSI(14) > 70
→ TRUE when RSI > 70 (overbought)</pre>

        <h3 style='color:{c.BLUE}'>< (Less Than)</h3>
        <p>TRUE if left side value is less than right side value.</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
RSI(14) < 30
→ TRUE when RSI < 30 (oversold)</pre>

        <h3 style='color:{c.BLUE}'>>= (Greater Than or Equal)</h3>
        <p>TRUE if left side is greater than OR equal to right side.</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Close >= Open
→ TRUE for bullish or doji candles</pre>

        <h3 style='color:{c.BLUE}'><= (Less Than or Equal)</h3>
        <p>TRUE if left side is less than OR equal to right side.</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Close <= Open
→ TRUE for bearish or doji candles</pre>

        <h3 style='color:{c.BLUE}'>== (Equal)</h3>
        <p>TRUE if values are equal (within floating-point tolerance).</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Close == Open
→ TRUE for doji candles</pre>

        <h3 style='color:{c.BLUE}'>!= (Not Equal)</h3>
        <p>TRUE if values are not equal.</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
Close != Open
→ TRUE for non-doji candles</pre>

        <h2 style='color:{c.GREEN}'>Range Operator</h2>

        <h3 style='color:{c.BLUE}'>between</h3>
        <p>TRUE when the left side value is between two right side values (inclusive).</p>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
RSI(14) between [30, 70]
→ TRUE when 30 <= RSI <= 70 (neutral zone)</pre>
        """

    def _get_shift_controls_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>⏱️ Shift Controls</h1>

        <p>Shift controls allow you to compare current values with historical values. Available for Indicators and Columns (not Scalars).</p>

        <h2 style='color:{c.GREEN}'>How Shift Works</h2>
        <p>The shift value determines how many bars to look back:</p>
        <ul>
            <li><b>shift: 0</b> - Current bar (most recent value)</li>
            <li><b>shift: 1</b> - Previous bar (1 bar ago)</li>
            <li><b>shift: 2</b> - 2 bars ago</li>
            <li><b>shift: n</b> - n bars ago</li>
        </ul>

        <h2 style='color:{c.GREEN}'>Common Shift Patterns</h2>

        <h3 style='color:{c.BLUE}'>1. Momentum Detection</h3>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
close > close.shift(1)
→ Current close higher than previous close (uptick)</pre>

        <h3 style='color:{c.BLUE}'>2. Trend Strength</h3>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
close > close.shift(5)
→ Current close higher than 5 bars ago (trending up)</pre>

        <h3 style='color:{c.BLUE}'>3. VWAP Slope</h3>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
vwap > vwap.shift(1)
→ VWAP rising (buying pressure increasing)</pre>

        <h3 style='color:{c.BLUE}'>4. Momentum Divergence</h3>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_MD}px; border-radius:{self._sp.RADIUS_SM}px;'>
close > close.shift(5) AND rsi < rsi.shift(5)
→ Price higher but momentum lower (bearish divergence)</pre>
        """

    def _get_weights_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>⚖️ Rule Weights</h1>

        <p>Rule weights are a key part of the confidence scoring system. Each rule can be assigned a weight from 0.1 to 5.0 that determines its importance in the final signal confidence calculation.</p>

        <h2 style='color:{c.GREEN}'>How Weights Work</h2>
        <ul>
            <li><b>Default weight:</b> 1.0</li>
            <li><b>Minimum:</b> 0.1 (very low importance)</li>
            <li><b>Maximum:</b> 5.0 (extremely high importance)</li>
            <li><b>Step:</b> 0.1 increments</li>
        </ul>

        <h2 style='color:{c.GREEN}'>Suggested Weights by Indicator Type</h2>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'>
                <th>Category</th>
                <th>Indicators</th>
                <th>Suggested Weight</th>
                <th>Reliability</th>
            </tr>
            <tr><td><b>Trend Strength</b></td><td>ADX, Supertrend</td><td><b>2.0</b></td><td>High</td></tr>
            <tr><td><b>Moving Average Crossovers</b></td><td>Golden/Death Cross</td><td><b>1.8-2.5</b></td><td>High</td></tr>
            <tr><td><b>MACD</b></td><td>MACD crossovers</td><td><b>1.8</b></td><td>Good</td></tr>
            <tr><td><b>Momentum</b></td><td>RSI, Stochastic</td><td><b>1.5</b></td><td>Medium</td></tr>
            <tr><td><b>Volatility</b></td><td>Bollinger Bands, ATR</td><td><b>1.3-1.5</b></td><td>Medium</td></tr>
            <tr><td><b>Volume</b></td><td>OBV, MFI</td><td><b>1.2-1.4</b></td><td>Low-Medium</td></tr>
            <tr><td><b>Supporting Conditions</b></td><td>Volume confirmation</td><td><b>1.0</b></td><td>Low</td></tr>
        </table>
        """

    def _get_confidence_calculation_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>📊 How Confidence is Calculated</h1>

        <h2 style='color:{c.GREEN}'>The Formula</h2>
        <div style='background:{c.BG_HOVER}; padding:{self._sp.PAD_XL}px; border-radius:{self._sp.RADIUS_LG}px; margin:{self._sp.PAD_XL}px 0; text-align:center;'>
            <h3>Confidence = (Sum of passed rule weights) / (Sum of all rule weights)</h3>
        </div>

        <h2 style='color:{c.GREEN}'>Step-by-Step Example</h2>

        <p>Consider a BUY_CALL group with 3 rules:</p>

        <table width='100%' border='1' cellpadding='8' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'>
                <th>Rule</th>
                <th>Weight</th>
                <th>Result</th>
            </tr>
            <tr><td>RSI(14) > 50</td><td>1.5</td><td style='color:{c.GREEN};'>✅ True</td></tr>
            <tr><td>MACD > Signal</td><td>2.0</td><td style='color:{c.GREEN};'>✅ True</td></tr>
            <tr><td>Close > EMA(20)</td><td>1.0</td><td style='color:{c.RED};'>❌ False</td></tr>
        </table>

        <h3 style='color:{c.BLUE}'>Calculation:</h3>
        <pre style='background:{c.BG_MAIN}; padding:{self._sp.PAD_LG}px; border-radius:{self._sp.RADIUS_LG}px;'>
Total weight = 1.5 + 2.0 + 1.0 = 4.5
Passed weight = 1.5 + 2.0 = 3.5
Confidence = 3.5 / 4.5 = 0.78 (78%)</pre>

        <h2 style='color:{c.GREEN}'>AND vs OR Logic</h2>

        <h3 style='color:{c.BLUE}'>AND Logic</h3>
        <ul>
            <li>Group fires ONLY if ALL rules are TRUE</li>
            <li>Confidence still calculated from passed weights</li>
            <li>Example: If one rule is FALSE, group doesn't fire even with 90% confidence</li>
        </ul>

        <h3 style='color:{c.BLUE}'>OR Logic</h3>
        <ul>
            <li>Group fires if ANY rule is TRUE</li>
            <li>Confidence reflects how many rules are true</li>
            <li>Can fire with low confidence (e.g., 30% if only one light rule true)</li>
        </ul>
        """

    def _get_thresholds_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>🎚️ Setting Confidence Thresholds</h1>

        <p>The confidence threshold determines how confident the system must be before generating a signal. You can adjust this in the title bar of the Strategy Editor.</p>

        <h2 style='color:{c.GREEN}'>Threshold Profiles</h2>

        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'>
                <th>Profile</th>
                <th>Threshold</th>
                <th>Description</th>
                <th>Best For</th>
            </tr>
            <tr><td><b>Conservative</b></td><td>0.7 (70%)</td><td>Only the strongest signals</td><td>Risk-averse traders</td></tr>
            <tr><td><b>Moderate</b></td><td>0.6 (60%)</td><td>Balanced approach</td><td>Most traders, default</td></tr>
            <tr><td><b>Aggressive</b></td><td>0.5 (50%)</td><td>More signals, accepts lower confidence</td><td>Scalpers, high-frequency</td></tr>
        </table>

        <h2 style='color:{c.GREEN}'>How to Choose Your Threshold</h2>

        <h3 style='color:{c.BLUE}'>Consider Your Trading Style:</h3>
        <ul>
            <li><b>Swing Trading:</b> Higher threshold (0.65-0.75)</li>
            <li><b>Day Trading:</b> Medium threshold (0.55-0.65)</li>
            <li><b>Scalping:</b> Lower threshold (0.45-0.55)</li>
        </ul>
        """

    def _get_creating_strategies_content(self) -> str:
        c = self._c
        return f"""
        <h2 style='color:{c.BLUE}'>➕ Creating New Strategies</h2>

        <h3 style='color:{c.GREEN}'>Method 1: From Scratch</h3>
        <ol>
            <li>Click the <b>"＋ New"</b> button in the left panel</li>
            <li>Enter a descriptive name (e.g., "EMA Crossover Strategy")</li>
            <li>The new strategy appears in the list with default settings</li>
        </ol>

        <h3 style='color:{c.GREEN}'>Method 2: Using Presets</h3>
        <ol>
            <li>Select a signal group tab (BUY_CALL, BUY_PUT, etc.)</li>
            <li>Click the <b>"📋 Load Preset"</b> dropdown</li>
            <li>Choose a preset that matches your trading style</li>
        </ol>

        <h3 style='color:{c.GREEN}'>Method 3: Import from JSON</h3>
        <ol>
            <li>Click the <b>"📥 Import"</b> button in the title bar</li>
            <li>Paste your JSON or load from file</li>
            <li>Click <b>"✓ Validate"</b> to check the format</li>
            <li>Click <b>"Import"</b> and enter a name</li>
        </ol>
        """

    def _get_activating_content(self) -> str:
        c = self._c
        return f"""
        <h2 style='color:{c.BLUE}'>⚡ Activating Strategies</h2>

        <p>The active strategy is used by the trading engine to generate signals. Only one strategy can be active at a time.</p>

        <h3 style='color:{c.GREEN}'>Activation Methods:</h3>
        <ul>
            <li><b>Double-click</b> a strategy in the list</li>
            <li>Select a strategy and click the <b>"⚡ Activate"</b> button in the left panel</li>
            <li>Select a strategy and click the <b>"⚡ Activate This Strategy"</b> button in the footer</li>
        </ul>

        <h3 style='color:{c.GREEN}'>Visual Indicators:</h3>
        <ul>
            <li>Active strategies are marked with <b>⚡</b> in the list</li>
            <li>The strategy name appears in <b><span style='color:{c.BLUE};'>blue</span></b></li>
            <li>The title bar shows an <b>"ACTIVE"</b> badge</li>
        </ul>
        """

    def _get_shortcuts_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>⌨️ Keyboard Shortcuts</h1>

        <h2 style='color:{c.GREEN}'>Global Shortcuts</h2>
        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'><th>Shortcut</th><th>Action</th></tr>
            <tr><td><code>Ctrl+S</code></td><td>Save current strategy</td></tr>
            <tr><td><code>Ctrl+N</code></td><td>Create new strategy</td></tr>
            <tr><td><code>Ctrl+D</code></td><td>Duplicate current strategy</td></tr>
            <tr><td><code>Ctrl+Shift+A</code></td><td>Activate current strategy</td></tr>
            <tr><td><code>Esc</code></td><td>Close editor / Cancel</td></tr>
            <tr><td><code>F1</code></td><td>Open help (this tab)</td></tr>
        </table>

        <h2 style='color:{c.GREEN}'>Navigation Shortcuts</h2>
        <table width='100%' border='1' cellpadding='10' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'><th>Shortcut</th><th>Action</th></tr>
            <tr><td><code>Ctrl+Tab</code></td><td>Next tab</td></tr>
            <tr><td><code>Ctrl+Shift+Tab</code></td><td>Previous tab</td></tr>
            <tr><td><code>Ctrl+1-4</code></td><td>Switch to tab 1-4</td></tr>
        </table>
        """

    def _get_faq_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>❓ Frequently Asked Questions</h1>

        <h3 style='color:{c.GREEN}'>Q: Why aren't my rules firing?</h3>
        <p><b>A:</b> Check these common issues:</p>
        <ul>
            <li>Verify the signal group is enabled (checkbox checked)</li>
            <li>Check your logic (AND requires ALL rules true)</li>
            <li>Ensure confidence is above the minimum threshold</li>
            <li>Verify indicator parameters are valid</li>
        </ul>

        <h3 style='color:{c.GREEN}'>Q: What's the difference between AND and OR logic?</h3>
        <p><b>A:</b> 
        <ul>
            <li><b>AND:</b> ALL rules must be true for the group to fire.</li>
            <li><b>OR:</b> ANY rule being true can fire the group.</li>
        </ul>
        </p>

        <h3 style='color:{c.GREEN}'>Q: How is confidence calculated?</h3>
        <p><b>A:</b> Confidence = (Sum of weights of passed rules) / (Sum of all rule weights).</p>

        <h3 style='color:{c.GREEN}'>Q: Why can't I delete the active strategy?</h3>
        <p><b>A:</b> The active strategy is currently in use. Activate another strategy first, then delete this one.</p>
        """

    def _get_errors_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>❌ Common Errors & Solutions</h1>

        <table width='100%' border='1' cellpadding='12' style='border-collapse: collapse;'>
            <tr style='background:{c.BG_HOVER};'>
                <th>Error Message</th>
                <th>Cause</th>
                <th>Solution</th>
            </tr>
            <tr>
                <td><b>"No rules defined"</b></td>
                <td>The signal group has no rules or is disabled</td>
                <td>Add at least one rule and ensure it's enabled</td>
            </tr>
            <tr>
                <td><b>"Invalid operator"</b></td>
                <td>Manual entry of operator instead of selection</td>
                <td>Always select operators from the dropdown</td>
            </tr>
            <tr>
                <td><b>"Parameter out of range"</b></td>
                <td>Indicator parameter outside valid range</td>
                <td>Check valid ranges: length (1-100), std (0.1-5)</td>
            </tr>
            <tr>
                <td><b>"Cannot delete active strategy"</b></td>
                <td>Attempting to delete the currently active strategy</td>
                <td>Activate another strategy first</td>
            </tr>
            <tr>
                <td><b>"JSON missing required fields"</b></td>
                <td>Imported JSON missing 'name' and 'engine'</td>
                <td>Ensure JSON includes both fields</td>
            </tr>
        </table>
        """

    def _get_best_practices_content(self) -> str:
        c = self._c
        return f"""
        <h1 style='color:{c.BLUE}'>✨ Best Practices</h1>

        <h2 style='color:{c.GREEN}'>Strategy Design</h2>

        <h3 style='color:{c.BLUE}'>1. Start Simple</h3>
        <ul>
            <li>Begin with 2-3 rules per signal group</li>
            <li>Test thoroughly before adding complexity</li>
            <li>Add one rule at a time and observe the impact</li>
        </ul>

        <h3 style='color:{c.BLUE}'>2. Combine Different Indicator Types</h3>
        <div style='background:{c.BG_HOVER}; padding:{self._sp.PAD_LG}px; border-radius:{self._sp.RADIUS_LG}px; margin:{self._sp.PAD_MD}px 0;'>
            <p><b style='color:{c.GREEN}'>✅ Good:</b> RSI (momentum) + EMA (trend) + Volume (confirmation)</p>
            <p><b style='color:{c.RED}'>❌ Avoid:</b> RSI + Stochastic + CCI (all momentum, redundant)</p>
        </div>

        <h3 style='color:{c.BLUE}'>3. Use Appropriate Weights</h3>
        <ul>
            <li>High Reliability (1.8-2.5): ADX, Supertrend, Golden Cross</li>
            <li>Good Reliability (1.5-1.8): MACD, RSI at extremes</li>
            <li>Medium Reliability (1.2-1.5): Bollinger Bands, Stochastic</li>
            <li>Supporting (1.0-1.2): Volume, derived columns</li>
        </ul>

        <h3 style='color:{c.BLUE}'>4. Set Realistic Confidence Thresholds</h3>
        <ul>
            <li>Conservative (0.7): For larger positions</li>
            <li>Moderate (0.6): Default, balanced approach</li>
            <li>Aggressive (0.5): For scalping, testing</li>
        </ul>
        """

    def load(self, strategy: Dict):
        """Load strategy data (no-op for help tab)"""
        pass

    def collect(self) -> Dict:
        """Collect help tab data (no-op)"""
        return {}