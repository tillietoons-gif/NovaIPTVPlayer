"""Nova IPTV Player - entry point.

Run with:  python main.py
"""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import __app_name__, __version__
from ui.main_window import MainWindow
from ui.theme import apply_theme


def _app_icon() -> QIcon:
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ("assets/icon.png", "assets/icon.ico"):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__app_name__)
    app.setWindowIcon(_app_icon())

    apply_theme(app)

    win = MainWindow()
    win.setMinimumSize(720, 500)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
