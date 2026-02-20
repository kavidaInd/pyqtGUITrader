#!/usr/bin/env python3
# PYQT: New entry point for PyQt5 application
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from TradingGUI import TradingGUI


def main():
    # PYQT: High-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Algo Trading Dashboard")

    window = TradingGUI()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()