"""Nova IPTV dark dashboard theme (violet accent).

Design tokens live in COLORS; build_stylesheet() compiles the full QSS.
No emojis anywhere in the UI — icons are drawn with QPainter (ui.widgets).
"""

from __future__ import annotations

from PySide6.QtGui import QFont

COLORS = {
    "bg": "#090b10",
    "surface": "#0f131d",
    "surface2": "#151b28",
    "card": "#181f2f",
    "card_hover": "#20293d",
    "border": "#222c3f",
    "border_light": "rgba(255, 255, 255, 0.08)",
    "border_glow": "rgba(139, 92, 246, 0.45)",
    "accent": "#8b5cf6",
    "accent_light": "#a78bfa",
    "accent2": "#6d28d9",
    "cyan": "#06b6d4",
    "cyan_glow": "rgba(6, 182, 212, 0.25)",
    "text": "#f8fafc",
    "muted": "#94a3b8",
    "green": "#10b981",
    "red": "#ef4444",
    "gold": "#f59e0b",
}

GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
    " stop:0 #8b5cf6, stop:0.6 #7c3aed, stop:1 #6d28d9)"
)
HERO_GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
    " stop:0 #1a152e, stop:0.45 #121626, stop:1 #0c0f18)"
)



def build_stylesheet() -> str:
    c = COLORS
    return f"""
* {{
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
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
    border: 1px solid rgba(139, 92, 246, 0.35);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 9pt;
}}

/* ================= sidebar ================= */
QWidget#sidebar {{
    background: {c["surface"]};
    border-right: 1px solid {c["border"]};
}}
QPushButton#navBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 11px;
    padding: 10px 14px;
    text-align: left;
    font-size: 10pt;
    font-weight: 500;
    color: {c["muted"]};
}}
QPushButton#navBtn:hover {{
    background: rgba(255, 255, 255, 0.04);
    color: {c["text"]};
    border: 1px solid rgba(255, 255, 255, 0.05);
}}
QPushButton#navBtn:checked {{
    background: {GRADIENT};
    color: white;
    font-weight: 700;
    border: 1px solid rgba(255, 255, 255, 0.15);
}}
QLabel#brandTitle {{
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 1px;
    color: #ffffff;
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
    border-bottom: 1px solid {c["border"]};
}}
QLabel#connPill {{
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 13px;
    padding: 5px 14px;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: {c["text"]};
}}
QLineEdit#searchBar {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 12px;
    padding: 9px 16px;
    font-size: 10pt;
    color: {c["text"]};
}}
QLineEdit#searchBar:focus {{
    border: 1px solid {c["accent"]};
    background: {c["card"]};
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
    background: {c["card_hover"]};
    border: 1px solid rgba(139, 92, 246, 0.65);
}}
QFrame#channelCard[selected="true"] {{
    background: #222b3e;
    border: 2px solid {c["accent"]};
}}
QWidget#logoWrap {{
    background: {c["surface"]};
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 10px;
}}
QLabel#liveBadge {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #ef4444, stop:1 #dc2626);
    color: white;
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 0.5px;
}}
QLabel#qualityBadge {{
    background: rgba(6, 182, 212, 0.18);
    color: #38bdf8;
    border: 1px solid rgba(6, 182, 212, 0.45);
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 0.5px;
}}
QLabel#lockBadge {{
    background: rgba(9, 11, 16, 210);
    border: 1px solid {c["border"]};
    border-radius: 12px;
}}
QLabel#recLabel {{
    color: {c["red"]};
    font-size: 10pt;
    font-weight: 800;
}}
QLabel#pinError {{
    color: {c["red"]};
    font-size: 9pt;
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
    background: {c["card_hover"]};
    border: 1px solid rgba(139, 92, 246, 0.65);
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
    background: {HERO_GRADIENT};
    border: 1px solid #2d264a;
    border-radius: 18px;
}}
QLabel#heroTitle {{
    font-size: 21pt;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.3px;
}}
QLabel#heroKicker {{
    font-size: 8.5pt;
    color: {c["accent_light"]};
    letter-spacing: 1.5px;
    font-weight: 700;
}}

/* ================= buttons ================= */
QPushButton#primaryBtn {{
    background: {GRADIENT};
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 10px;
    padding: 10px 22px;
    font-weight: 700;
    font-size: 9.5pt;
}}
QPushButton#primaryBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #9d71f7, stop:0.6 #8b5cf6, stop:1 #7c3aed);
    border-color: rgba(255, 255, 255, 0.25);
}}
QPushButton#primaryBtn:disabled {{
    background: {c["surface2"]};
    color: {c["muted"]};
    border-color: transparent;
}}
QPushButton#outlineBtn {{
    background: rgba(255, 255, 255, 0.03);
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 9px 20px;
    font-size: 9.5pt;
    font-weight: 600;
}}
QPushButton#outlineBtn:hover {{
    background: rgba(139, 92, 246, 0.1);
    border-color: {c["accent"]};
    color: white;
}}
QPushButton#dangerBtn {{
    background: rgba(239, 68, 68, 0.08);
    color: {c["red"]};
    border: 1px solid rgba(239, 68, 68, 0.6);
    border-radius: 10px;
    padding: 9px 20px;
    font-size: 9.5pt;
    font-weight: 600;
}}
QPushButton#dangerBtn:hover {{
    background: {c["red"]};
    color: white;
    border-color: {c["red"]};
}}
/* provider switcher button (sidebar) */
QPushButton#providerBtn {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 9pt;
    text-align: left;
    color: {c["text"]};
}}
QPushButton#providerBtn:hover {{
    border-color: {c["accent"]};
    background: {c["card"]};
}}
/* login screen */
QWidget#loginOverlay {{
    background: {c["bg"]};
}}
QFrame#loginCard {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: 16px;
}}
QLabel#loginSub {{
    color: {c["muted"]};
    font-size: 10pt;
}}
QPushButton#loginTab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    color: {c["muted"]};
    font-size: 10pt;
    font-weight: 600;
    padding: 10px 16px;
}}
QPushButton#loginTab:checked {{
    color: {c["text"]};
    border-bottom: 2px solid {c["accent"]};
}}
QLabel#loginError {{
    color: {c["red"]};
    font-size: 9pt;
}}
/* inactive-account banner */
QFrame#accountBanner {{
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid {c["red"]};
    border-radius: 10px;
    margin: 8px 16px 0px 16px;
}}
/* dialogs */
QLabel#dlgTitle {{
    font-size: 14pt;
    font-weight: 700;
}}
QLabel#goldLabel {{
    color: {c["gold"]};
    font-weight: 700;
    font-size: 11pt;
}}
QLabel#plotLabel {{
    color: {c["text"]};
    font-size: 10pt;
    line-height: 1.4;
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
    background: {c["card_hover"]};
}}
QPushButton#transportBtn {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 16px;
    padding: 6px;
}}
QPushButton#transportBtn:hover {{
    border-color: {c["accent"]};
    background: {c["card_hover"]};
}}
QPushButton#transportHeroBtn {{
    background: {GRADIENT};
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 22px;
    padding: 6px;
}}
QPushButton#transportHeroBtn:hover {{
    background: {c["accent_light"]};
    border-color: white;
}}
QPushButton#transportHeroBtn:pressed {{
    background: {c["accent2"]};
}}

/* ================= sections / lists ================= */
QLabel#sectionTitle {{
    font-size: 13pt;
    font-weight: 700;
}}
QPushButton#viewAllBtn {{
    background: transparent;
    border: none;
    color: {c["accent_light"]};
    font-size: 10pt;
    font-weight: 600;
}}
QPushButton#viewAllBtn:hover {{
    color: white;
}}
QLabel#pageTitle {{
    font-size: 17pt;
    font-weight: 800;
    letter-spacing: -0.2px;
}}
QLabel#greeting {{
    font-size: 21pt;
    font-weight: 800;
    letter-spacing: -0.3px;
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
    border-left: 1px solid {c["border"]};
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
    border-top: 1px solid {c["border"]};
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
    border-radius: 9px;
    padding: 7px 12px;
    min-width: 140px;
    color: {c["text"]};
}}
QComboBox:hover {{
    border-color: {c["accent"]};
}}
QComboBox QAbstractItemView {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: rgba(139, 92, 246, 0.4);
    selection-color: white;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {c["surface2"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: #ffffff;
    border: 2px solid {c["accent"]};
}}
QSlider::handle:horizontal:hover {{
    background: {c["accent_light"]};
    border: 2px solid #ffffff;
}}
QSlider::sub-page:horizontal {{
    background: {GRADIENT};
    border-radius: 2px;
}}
QSlider#npSlider::groove:horizontal {{
    height: 4px;
    background: {c["surface"]};
    border-radius: 2px;
}}
QSlider#npSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
    background: #ffffff;
    border: 2px solid {c["accent"]};
}}
QSlider#npSlider::sub-page:horizontal {{
    background: {GRADIENT};
    border-radius: 2px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 7px;
    margin: 3px 1px 3px 1px;
}}
QScrollBar::handle:vertical {{
    background: rgba(148, 163, 184, 0.25);
    border-radius: 3px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(139, 92, 246, 0.7);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 7px;
    margin: 1px 3px 1px 3px;
}}
QScrollBar::handle:horizontal {{
    background: rgba(148, 163, 184, 0.25);
    border-radius: 3px;
    min-width: 36px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(139, 92, 246, 0.7);
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ================= splitter ================= */
QSplitter#mainSplitter {{
    background: transparent;
}}
QSplitter#mainSplitter::handle {{
    background: {c["border"]};
    width: 3px;
}}
QSplitter#mainSplitter::handle:hover {{
    background: {c["accent"]};
}}
QSplitter#mainSplitter::handle:pressed {{
    background: {c["accent_light"]};
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
    color: {c["accent_light"]};
    font-weight: 600;
}}
QDialog {{
    background: {c["surface"]};
}}
QDialog QLabel {{
    color: {c["text"]};
}}
QDialog#shortcutsDialog {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: 14px;
}}
QLabel#keyBadge {{
    background: {c["card"]};
    color: {c["accent_light"]};
    border: 1px solid #313847;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 9pt;
    font-weight: 700;
    font-family: "Consolas", "Courier New", monospace;
    min-width: 60px;
}}
QLabel#keyDesc {{
    font-size: 10pt;
    color: {c["text"]};
}}
QLineEdit, QSpinBox {{
    background: {c["surface2"]};
    border: 1px solid {c["border"]};
    border-radius: 9px;
    padding: 8px 12px;
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
    background: rgba(139, 92, 246, 0.35);
    border-radius: 6px;
}}
QMenu {{
    background: {c["card"]};
    border: 1px solid rgba(139, 92, 246, 0.25);
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 18px;
    border-radius: 6px;
    color: {c["text"]};
}}
QMenu::item:selected {{
    background: {c["accent"]};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {c["border"]};
    margin: 4px 6px;
}}
QCheckBox {{
    spacing: 8px;
}}

/* ================= responsive / overlay ================= */
QWidget#scrim {{
    background: rgba(4, 6, 10, 165);
}}
QWidget#drawerPanel {{
    background: {c["surface"]};
    border-left: 1px solid {c["border"]};
}}
QPushButton#fabBtn {{
    background: {GRADIENT};
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 28px;
    font-weight: 700;
}}
QPushButton#fabBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #9d71f7, stop:0.6 #8b5cf6, stop:1 #7c3aed);
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

/* ================= advanced player overlays ================= */
QFrame#zapperOverlay {{
    background: rgba(10, 14, 24, 0.96);
    border: 1px solid rgba(139, 92, 246, 0.55);
    border-radius: 16px;
}}
QListWidget#zapperList {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
}}
QListWidget#zapperList::item {{
    background: rgba(21, 27, 40, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 10px;
    padding: 8px 10px;
    margin-bottom: 6px;
    color: {c["text"]};
}}
QListWidget#zapperList::item:hover {{
    background: rgba(32, 41, 61, 0.95);
    border: 1px solid rgba(139, 92, 246, 0.5);
}}
QListWidget#zapperList::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(139, 92, 246, 0.35), stop:1 rgba(109, 40, 217, 0.45));
    border: 1.5px solid {c["accent"]};
}}

QFrame#statsHud {{
    background: rgba(9, 12, 19, 0.93);
    border: 1px solid rgba(6, 182, 212, 0.5);
    border-radius: 14px;
}}
QLabel#statsTitle {{
    color: {c["cyan"]};
    font-size: 11pt;
    font-weight: 800;
    letter-spacing: 0.5px;
}}
QLabel#statsKey {{
    color: {c["muted"]};
    font-size: 9pt;
    font-weight: 600;
}}
QLabel#statsVal {{
    color: #ffffff;
    font-size: 9pt;
    font-weight: 700;
    font-family: monospace;
}}

QFrame#volumeToast {{
    background: rgba(15, 19, 29, 0.94);
    border: 1.5px solid {c["accent"]};
    border-radius: 20px;
    padding: 8px 18px;
}}
QLabel#channelNumberOsd {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(139, 92, 246, 0.95), stop:1 rgba(109, 40, 217, 0.95));
    color: white;
    font-size: 16pt;
    font-weight: 800;
    border: 2px solid rgba(255, 255, 255, 0.35);
    border-radius: 12px;
    padding: 6px 18px;
    letter-spacing: 1px;
}}
QLabel#sleepTimerBadge {{
    background: rgba(245, 158, 11, 0.18);
    border: 1px solid rgba(245, 158, 11, 0.5);
    border-radius: 12px;
    color: #fbbf24;
    font-weight: 700;
    font-size: 8.5pt;
    padding: 3px 10px;
}}

QPushButton#filterChip {{
    background: rgba(255, 255, 255, 0.04);
    color: {c["muted"]};
    border: 1px solid {c["border"]};
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 9pt;
    font-weight: 600;
}}
QPushButton#filterChip:hover {{
    background: rgba(255, 255, 255, 0.08);
    color: {c["text"]};
    border-color: rgba(139, 92, 246, 0.4);
}}
QPushButton#filterChip:checked {{
    background: {GRADIENT};
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
    font-weight: 700;
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
