"""Dark glassy theme: QSS, palette constants, font setup."""

from __future__ import annotations

from PySide6.QtGui import QFont

ACCENT = "#00d4ff"
ACCENT_DIM = "#0099bb"
BG_DEEP = "#0b0e14"
BG_PANEL = "#11151d"
BG_CARD = "#161c27"
BG_HOVER = "#1c2432"
BORDER = "#232c3d"
TEXT_MAIN = "#e8eef7"
TEXT_DIM = "#8b95a9"

DARK_QSS = f"""
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    color: {TEXT_MAIN};
}}
QMainWindow, QWidget#central {{
    background: {BG_DEEP};
}}
/* ---------- sidebar ---------- */
QWidget#sidebar {{
    background: {BG_PANEL};
    border-right: 1px solid {BORDER};
}}
QPushButton#navBtn {{
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: left;
    font-size: 14px;
    color: {TEXT_DIM};
}}
QPushButton#navBtn:hover {{
    background: {BG_HOVER};
    color: {TEXT_MAIN};
}}
QPushButton#navBtn:checked {{
    background: rgba(0, 212, 255, 0.14);
    color: {ACCENT};
    border: 1px solid rgba(0, 212, 255, 0.35);
}}
QLabel#brandLabel {{
    font-size: 20px;
    font-weight: 800;
    color: {TEXT_MAIN};
    padding: 16px 14px 4px 14px;
}}
QLabel#brandAccent {{
    font-size: 20px;
    font-weight: 800;
    color: {ACCENT};
}}
/* ---------- cards ---------- */
QFrame#channelCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#channelCard:hover {{
    border: 1px solid {ACCENT_DIM};
    background: {BG_HOVER};
}}
QLabel#cardName {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#cardMeta {{
    font-size: 11px;
    color: {TEXT_DIM};
}}
QPushButton#favBtn {{
    background: transparent;
    border: none;
    font-size: 16px;
    color: {TEXT_DIM};
}}
QPushButton#favBtn:checked {{
    color: {ACCENT};
}}
/* ---------- inputs ---------- */
QLineEdit#searchBar {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 14px;
    font-size: 14px;
}}
QLineEdit#searchBar:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    selection-background-color: rgba(0, 212, 255, 0.2);
}}
/* ---------- player bar ---------- */
QWidget#playerBar {{
    background: {BG_PANEL};
    border-top: 1px solid {BORDER};
}}
QPushButton#ctlBtn {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 14px;
}}
QPushButton#ctlBtn:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {BORDER};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -4px 0;
    border-radius: 7px;
    background: {ACCENT};
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 3px;
}}
QFrame#videoFrame {{
    background: #000;
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#nowPlaying {{
    font-size: 14px;
    font-weight: 700;
}}
QLabel#nowNext {{
    font-size: 12px;
    color: {TEXT_DIM};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_DIM};
}}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: {BG_CARD};
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: {TEXT_DIM};
}}
QTabBar::tab:selected {{
    background: {BG_HOVER};
    color: {ACCENT};
}}
QDialog {{
    background: {BG_PANEL};
}}
QPushButton#primaryBtn {{
    background: {ACCENT};
    color: #04121a;
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-weight: 700;
}}
QPushButton#primaryBtn:hover {{
    background: #33e0ff;
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(DARK_QSS)
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)
