"""Nova IPTV dark dashboard theme (violet accent).

Design tokens live in COLORS; build_stylesheet() compiles the full QSS.
No emojis anywhere in the UI — icons are drawn with QPainter (ui.widgets).
"""

from __future__ import annotations

from PySide6.QtGui import QFont

COLORS = {
    "bg": "#0b0d13",
    "surface": "#141821",
    "surface2": "#1a1f2b",
    "card": "#1e2330",
    "border": "#232b3d",
    "accent": "#8b5cf6",
    "accent2": "#6d28d9",
    "text": "#f2f3f7",
    "muted": "#8b91a7",
    "green": "#22c55e",
    "red": "#ef4444",
}

GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:0,"
    " stop:0 #8b5cf6, stop:1 #6d28d9)"
)


def build_stylesheet() -> str:
    c = COLORS
    return f"""
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
    color: {c["text"]};
}}
QMainWindow {{
    background: {c["bg"]};
}}
QWidget#central {{
    background: {c["bg"]};
}}
QToolTip {{
    background: {c["surface2"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    padding: 4px 8px;
}}

/* ================= sidebar ================= */
QWidget#sidebar {{
    background: {c["surface"]};
}}
QPushButton#navBtn {{
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 10px 12px;
    text-align: left;
    font-size: 10pt;
    color: {c["muted"]};
}}
QPushButton#navBtn:hover {{
    background: {c["surface2"]};
    color: {c["text"]};
}}
QPushButton#navBtn:checked {{
    background: {GRADIENT};
    color: white;
    font-weight: 600;
}}
QLabel#brandTitle {{
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 1px;
}}
QWidget#sideDivider {{
    background: {c["border"]};
    max-height: 1px;
    min-height: 1px;
}}
QLabel#versionLabel {{
    color: {c["muted"]};
    font-size: 9pt;
}}
QLabel#userName {{
    font-size: 10pt;
    font-weight: 600;
}}

/* ================= top bar ================= */
QWidget#topbar {{
    background: {c["bg"]};
}}
QLabel#connPill {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLineEdit#searchBar {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 10pt;
    color: {c["text"]};
}}
QLineEdit#searchBar:focus {{
    border: 1px solid {c["accent"]};
}}
QPushButton#iconBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
}}
QPushButton#iconBtn:hover {{
    background: {c["surface2"]};
}}
QPushButton#winBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px;
    color: {c["muted"]};
}}
QPushButton#winBtn:hover {{
    background: {c["surface2"]};
    color: {c["text"]};
}}
QPushButton#winBtn[danger="true"]:hover {{
    background: #e81123;
    color: white;
}}

/* ================= cards ================= */
QFrame#channelCard {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 14px;
}}
QFrame#channelCard:hover {{
    border: 1px solid {c["accent"]};
}}
QFrame#channelCard[selected="true"] {{
    border: 2px solid {c["accent"]};
}}
QWidget#logoWrap {{
    background: {c["surface"]};
    border-radius: 10px;
}}
QLabel#liveBadge {{
    background: {c["red"]};
    color: white;
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 8pt;
    font-weight: 800;
}}
QLabel#qualityBadge {{
    background: rgba(0, 0, 0, 120);
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: 700;
}}
QLabel#cardName {{
    font-size: 10pt;
    font-weight: 600;
}}
QLabel#cardMeta {{
    font-size: 9pt;
    color: {c["muted"]};
}}
QPushButton#favBtn {{
    background: transparent;
    border: none;
    color: {c["muted"]};
    padding: 2px;
}}
QPushButton#favBtn:hover {{
    color: {c["accent"]};
}}
QPushButton#favBtn:checked {{
    color: {c["accent"]};
}}

QFrame#posterCard {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 14px;
}}
QFrame#posterCard:hover {{
    border: 1px solid {c["accent"]};
}}
QProgressBar#miniProgress {{
    background: {c["surface"]};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar#miniProgress::chunk {{
    background: {GRADIENT};
    border-radius: 3px;
}}

QFrame#heroCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #191423, stop:0.55 #141821, stop:1 #141821);
    border: 1px solid {c["border"]};
    border-radius: 16px;
}}
QLabel#heroTitle {{
    font-size: 20pt;
    font-weight: 800;
}}
QLabel#heroKicker {{
    font-size: 9pt;
    color: {c["muted"]};
    letter-spacing: 1px;
    font-weight: 600;
}}

/* ================= buttons ================= */
QPushButton#primaryBtn {{
    background: {GRADIENT};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 22px;
    font-weight: 700;
    font-size: 10pt;
}}
QPushButton#primaryBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #9d71f7, stop:1 #7c3aed);
}}
QPushButton#primaryBtn:disabled {{
    background: {c["surface2"]};
    color: {c["muted"]};
}}
QPushButton#outlineBtn {{
    background: transparent;
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 9px 20px;
    font-size: 10pt;
}}
QPushButton#outlineBtn:hover {{
    border-color: {c["accent"]};
}}
QPushButton#ctlBtn {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 10pt;
}}
QPushButton#ctlBtn:hover {{
    border-color: {c["accent"]};
}}
QPushButton#transportBtn {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 18px;
    padding: 8px;
}}
QPushButton#transportBtn:hover {{
    border-color: {c["accent"]};
}}

/* ================= sections / lists ================= */
QLabel#sectionTitle {{
    font-size: 13pt;
    font-weight: 700;
}}
QPushButton#viewAllBtn {{
    background: transparent;
    border: none;
    color: {c["accent"]};
    font-size: 10pt;
    font-weight: 600;
}}
QPushButton#viewAllBtn:hover {{
    text-decoration: underline;
}}
QLabel#pageTitle {{
    font-size: 16pt;
    font-weight: 800;
}}
QLabel#greeting {{
    font-size: 20pt;
    font-weight: 800;
}}
QLabel#greetingSub {{
    font-size: 11pt;
    color: {c["muted"]};
}}
QLabel#dateLabel {{
    font-size: 9pt;
    color: {c["muted"]};
}}

/* ================= right panel ================= */
QWidget#rightPanel {{
    background: {c["surface"]};
}}
QFrame#sideCard {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 14px;
}}
QLabel#sideTitle {{
    font-size: 11pt;
    font-weight: 700;
}}
QLabel#upTime {{
    font-size: 9pt;
    color: {c["muted"]};
}}
QLabel#upTitle {{
    font-size: 10pt;
    font-weight: 600;
}}
QLabel#upChannel {{
    font-size: 9pt;
    color: {c["muted"]};
}}
QProgressBar#epgProgress {{
    background: {c["surface"]};
    border: none;
    border-radius: 4px;
    height: 8px;
}}
QProgressBar#epgProgress::chunk {{
    background: {GRADIENT};
    border-radius: 4px;
}}
QFrame#videoThumb {{
    background: #000;
    border: 1px solid {c["border"]};
    border-radius: 10px;
}}
QLabel#thumbPlaceholder {{
    color: {c["muted"]};
    font-size: 9pt;
}}

/* ================= status bar ================= */
QWidget#statusbar {{
    background: {c["surface"]};
}}
QLabel#statusText {{
    font-size: 9pt;
    color: {c["muted"]};
}}
QLabel#statusDot {{
    font-size: 10pt;
}}

/* ================= inputs / misc ================= */
QComboBox {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 7px 10px;
    min-width: 140px;
}}
QComboBox QAbstractItemView {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    selection-background-color: rgba(139, 92, 246, 40);
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {c["surface"]};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -4px 0;
    border-radius: 7px;
    background: {c["accent"]};
}}
QSlider::sub-page:horizontal {{
    background: {c["accent"]};
    border-radius: 3px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {c["border"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {c["border"]};
    border-radius: 5px;
    min-width: 30px;
}}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: {c["surface2"]};
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: {c["muted"]};
}}
QTabBar::tab:selected {{
    background: {c["card"]};
    color: {c["accent"]};
}}
QDialog {{
    background: {c["surface"]};
}}
QDialog QLabel {{
    color: {c["text"]};
}}
QLineEdit, QSpinBox {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {c["accent"]};
}}
QLineEdit:focus, QSpinBox:focus {{
    border: 1px solid {c["accent"]};
}}
QListWidget {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
}}
QListWidget::item {{
    padding: 6px;
}}
QListWidget::item:selected {{
    background: rgba(139, 92, 246, 40);
    border-radius: 6px;
}}
QMenu {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {c["surface2"]};
}}
QCheckBox {{
    spacing: 8px;
}}

/* ================= responsive / overlay ================= */
QWidget#scrim {{
    background: rgba(4, 6, 10, 150);
}}
QWidget#drawerPanel {{
    background: {c["surface"]};
    border-left: 1px solid {c["border"]};
}}
QPushButton#fabBtn {{
    background: {GRADIENT};
    color: white;
    border: none;
    border-radius: 28px;
    font-weight: 700;
}}
QPushButton#fabBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #9d71f7, stop:1 #7c3aed);
}}
QPushButton#fabBtn:pressed {{
    background: {c["accent2"]};
}}
QFrame#skeletonCard {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 14px;
}}
QLabel#emptyTitle {{
    font-size: 14pt;
    font-weight: 700;
}}
QLabel#emptySub {{
    font-size: 10pt;
    color: {c["muted"]};
}}
QFrame#searchOverlay {{
    background: {c["card"]};
    border: 1px solid {c["accent"]};
    border-radius: 14px;
}}
QFrame#emptyWrap {{
    background: transparent;
    border: 1px dashed {c["border"]};
    border-radius: 14px;
}}

/* ================= states ================= */
QPushButton#primaryBtn:pressed {{
    background: {c["accent2"]};
}}
QPushButton#outlineBtn:pressed {{
    background: {c["surface2"]};
}}
QPushButton#iconBtn:pressed {{
    background: {c["surface"]};
}}
QPushButton#navBtn:pressed {{
    background: {c["surface"]};
}}
QPushButton#navBtn:focus {{
    border: 1px solid rgba(139, 92, 246, 120);
}}
QPushButton#transportBtn:pressed {{
    background: {c["surface"]};
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(build_stylesheet())
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)


# -- UI-only preferences (kept out of app/ so the UI layer owns them) ----------

class UiPrefs:
    """Tiny QSettings wrapper for presentation prefs (same store as AppConfig)."""

    def __init__(self) -> None:
        from PySide6.QtCore import QSettings
        from app import __app_name__
        self._s = QSettings(__app_name__, __app_name__)

    @property
    def reduce_animations(self) -> bool:
        return self._s.value("ui/reduce_animations", False, type=bool)

    @reduce_animations.setter
    def reduce_animations(self, value: bool) -> None:
        self._s.setValue("ui/reduce_animations", bool(value))

    def sync(self) -> None:
        self._s.sync()


def animations_enabled() -> bool:
    """False when the user asked for reduced motion."""
    try:
        return not UiPrefs().reduce_animations
    except Exception:
        return True
