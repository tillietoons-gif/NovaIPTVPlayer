"""Nova IPTV Player - entry point.

Run with:  python main.py
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app import __app_name__, __version__
from ui.main_window import MainWindow
from ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__app_name__)

    apply_theme(app)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
