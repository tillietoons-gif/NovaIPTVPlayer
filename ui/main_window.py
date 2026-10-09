"""Main window: frameless Nova IPTV dashboard (sidebar, top bar, pages,
right Now-Playing panel, status bar)."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone, timedelta
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import (
    Qt, QThread, Signal, QPoint, QTimer, QPropertyAnimation,
    QAbstractAnimation, QUrl, QStandardPaths, QEvent,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QLabel, QSlider, QComboBox, QMessageBox,
    QScrollArea, QDialog, QDialogButtonBox, QMenu, QFormLayout,
    QLineEdit, QAbstractButton, QGraphicsOpacityEffect, QProgressBar,
    QSplitter, QSplitterHandle,
)


from app import __app_name__, __version__
from app.config import AppConfig
from app.epg import EPGManager
from app.external_player import launch_player, detect_players
from app.favorites import FavoritesStore
from app.history import HistoryStore
from app.models import (
    Channel, EPGProgram, xtream_live_to_channels, xtream_vod_to_channels,
    xtream_vod_detail_to_channel, xtream_series_to_channels,
    xtream_episodes_to_channels,
)
from app.player import Player
from app.parental import ParentalControls
from app.playlist import (
    load_playlist, categories, filter_channels,
)
from app.profiles import ProfileStore, ProviderProfile, migrate_legacy
from app.resume import ResumeStore
from app.xtream import XtreamClient, XtreamError
from ui.dialogs import AddPlaylistDialog, SettingsDialog, PinDialog, ShortcutsDialog
from ui.login import LoginScreen
from ui.theme import COLORS, animations_enabled
from ui.widgets import (
    ChannelGrid, SearchBar, VideoWidget, NavButton, IconButton, WinButton,
    SectionHeader, StatPill, ChannelCard, PosterCard, HeroCard,
    LogoLabel, brand_pixmap, avatar_pixmap, make_icon, poster_pixmap,
    ElidedLabel, EmptyState, SkeletonCard, Drawer, AudioVisualizer,
)



# -- background loaders (Qt threads, not asyncio: simpler on Windows) --------

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str, max_len: int = 60) -> str:
    """Make a channel name safe for use as a file name."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", (name or "").strip())
    cleaned = cleaned.strip().strip(".")
    return cleaned[:max_len] or "recording"


def _fmt_time(seconds: float) -> str:
    """Format seconds as m:ss or h:mm:ss."""
    s = max(0, int(seconds))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

class _PlaylistLoader(QThread):
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source

    def run(self) -> None:  # worker thread
        try:
            channels = load_playlist(self.source)
            self.finished_ok.emit(channels)
        except Exception as exc:
            self.failed.emit(str(exc))


class _EpgLoader(QThread):
    finished_ok = Signal(int)
    failed = Signal(str)

    def __init__(self, manager: EPGManager, source: str) -> None:
        super().__init__()
        self.manager = manager
        self.source = source

    def run(self) -> None:  # worker thread
        try:
            count = self.manager.load(self.source)
            self.finished_ok.emit(count)
        except Exception as exc:
            self.failed.emit(str(exc))


class _XtreamLoader(QThread):
    """Log in to an Xtream panel and pull live/VOD/series listings."""

    finished_ok = Signal(object)  # payload dict (client, user_info, channels…)
    failed = Signal(str)

    def __init__(self, profile: ProviderProfile) -> None:
        super().__init__()
        self.profile = profile

    def run(self) -> None:  # worker thread
        try:
            client = XtreamClient(self.profile.server,
                                  self.profile.username,
                                  self.profile.password)
            info = client.login()
            pid = self.profile.id

            live_streams = client.live_streams()
            vod_streams = client.vod_streams()
            series_entries = client.series_list()
            live_cats = dict(client.live_categories())
            vod_cats = dict(client.vod_categories())
            series_cats = dict(client.series_categories())

            live = xtream_live_to_channels(client, live_streams, pid)
            for ch, s in zip(live, live_streams):
                ch.group = live_cats.get(s.get("category_id", ""), "")
            vod = xtream_vod_to_channels(client, vod_streams, pid)
            for ch, s in zip(vod, vod_streams):
                ch.group = vod_cats.get(s.get("category_id", ""), "")
            series = xtream_series_to_channels(client, series_entries, pid)
            for ch, s in zip(series, series_entries):
                ch.group = series_cats.get(s.get("category_id", ""), "")

            self.finished_ok.emit({
                "client": client,
                "user_info": info["user_info"],
                "server_info": info["server_info"],
                "channels": live + vod + series,
                "epg_url": client.xmltv_url(),
            })
        except XtreamError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # never crash the thread silently
            self.failed.emit(f"Unexpected error: {exc}")


class _SeriesInfoLoader(QThread):
    """Fetch series_info() (seasons + episodes) for one series."""

    finished_ok = Signal(object)  # {"series_id": ..., "info": ...}
    failed = Signal(str)

    def __init__(self, client: XtreamClient, series_id: str) -> None:
        super().__init__()
        self.client = client
        self.series_id = series_id

    def run(self) -> None:  # worker thread
        try:
            info = self.client.series_info(self.series_id)
            self.finished_ok.emit(
                {"series_id": self.series_id, "info": info})
        except XtreamError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")


class _VodInfoLoader(QThread):
    """Fetch vod_info() for one movie."""

    finished_ok = Signal(object)  # vod_info dict
    failed = Signal(str)

    def __init__(self, client: XtreamClient, vod_id: str) -> None:
        super().__init__()
        self.client = client
        self.vod_id = vod_id

    def run(self) -> None:  # worker thread
        try:
            self.finished_ok.emit(self.client.vod_info(self.vod_id))
        except XtreamError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")


# -- small helpers ---------------------------------------------------------------

class _SidebarSplitterHandle(QSplitterHandle):
    def __init__(self, orientation: Qt.Orientation, parent: _SidebarSplitter) -> None:
        super().__init__(orientation, parent)
        self.setCursor(Qt.SplitHCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            splitter = self.splitter()
            if hasattr(splitter, "toggle_collapse"):
                splitter.toggle_collapse()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


class _SidebarSplitter(QSplitter):
    collapse_toggled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setObjectName("mainSplitter")
        self.setChildrenCollapsible(False)

    def createHandle(self) -> QSplitterHandle:  # noqa: N802
        return _SidebarSplitterHandle(self.orientation(), self)

    def toggle_collapse(self) -> None:
        self.collapse_toggled.emit()


class _TitleBar(QWidget):

    """Drag region for the frameless window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topbar")
        self._drag_offset = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window().pos())
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(
                event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None


class _ClickableRow(QFrame):
    clicked = Signal(object)

    def __init__(self, payload=None, parent=None) -> None:
        super().__init__(parent)
        self._payload = payload
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._payload)
        super().mousePressEvent(event)


class _PipWindow(QWidget):
    """Floating Picture-in-Picture window (always on top, resizable, frameless)."""

    closed = Signal()

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.main: MainWindow = main_window
        self.setWindowTitle("Nova IPTV — Picture-in-Picture")
        self.resize(440, 248)
        self.setMinimumSize(280, 158)
        self.setStyleSheet(f"background-color: {COLORS['bg']}; border: 1px solid {COLORS['border']};")
        self.setMouseTracking(True)
        self._drag_pos = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video = VideoWidget(self, placeholder="")
        self.video.setMouseTracking(True)
        if hasattr(self.main, "thumb_video") and hasattr(self.main.thumb_video, "aspect_ratio"):
            self.video.set_aspect_ratio(self.main.thumb_video.aspect_ratio())
        self.video.installEventFilter(self)
        layout.addWidget(self.video)

        # Floating overlay top bar
        self.overlay = QFrame(self)
        self.overlay.setObjectName("pipOverlay")
        self.overlay.setStyleSheet(f"""
            QFrame#pipOverlay {{
                background: rgba(8, 10, 15, 220);
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        olay = QHBoxLayout(self.overlay)
        olay.setContentsMargins(8, 6, 8, 6)
        olay.setSpacing(6)

        ch = self.main._current_channel
        self.title_lbl = QLabel(ch.name if ch else "Nova IPTV")
        self.title_lbl.setStyleSheet("color: white; font-weight: 600; font-size: 9pt;")
        olay.addWidget(self.title_lbl, 1)

        # Back to app
        ret_btn = QPushButton()
        ret_btn.setIcon(make_icon("back", 14, COLORS["text"]))
        ret_btn.setToolTip("Return to App")
        ret_btn.setFixedSize(26, 26)
        ret_btn.setCursor(Qt.PointingHandCursor)
        ret_btn.setStyleSheet(f"background: {COLORS['surface']}; border-radius: 13px; border: none;")
        ret_btn.clicked.connect(self._restore_app)
        olay.addWidget(ret_btn)

        # Play / Pause
        self.pp_btn = QPushButton()
        self.pp_btn.setIcon(make_icon("pause", 14, "white"))
        self.pp_btn.setToolTip("Play / Pause (Space)")
        self.pp_btn.setFixedSize(26, 26)
        self.pp_btn.setCursor(Qt.PointingHandCursor)
        self.pp_btn.setStyleSheet(f"background: {COLORS['accent']}; border-radius: 13px; border: none;")
        self.pp_btn.clicked.connect(self.main._toggle_pause)
        olay.addWidget(self.pp_btn)

        # Fullscreen
        fs_btn = QPushButton()
        fs_btn.setIcon(make_icon("expand", 14, COLORS["text"]))
        fs_btn.setToolTip("Fullscreen (F)")
        fs_btn.setFixedSize(26, 26)
        fs_btn.setCursor(Qt.PointingHandCursor)
        fs_btn.setStyleSheet(f"background: {COLORS['surface']}; border-radius: 13px; border: none;")
        fs_btn.clicked.connect(self._go_fullscreen)
        olay.addWidget(fs_btn)

        # Close PiP
        close_btn = QPushButton()
        close_btn.setIcon(make_icon("close", 14, COLORS["text"]))
        close_btn.setToolTip("Exit PiP (P / Esc)")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"background: {COLORS['surface']}; border-radius: 13px; border: none;")
        close_btn.clicked.connect(self.close)
        olay.addWidget(close_btn)

        self.overlay.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setInterval(2200)
        self._hide_timer.timeout.connect(self._auto_hide)

        self.main.player.state_changed.connect(self._on_player_state)

    def _auto_hide(self) -> None:
        if not self.overlay.underMouse():
            self.overlay.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), 38)
        self.overlay.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.video:
            if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress):
                self.overlay.show()
                self.overlay.raise_()
                self._hide_timer.start()
            elif event.type() == QEvent.MouseButtonDblClick:
                self._go_fullscreen()
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self.overlay.show()
        self.overlay.raise_()
        self._hide_timer.start()
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_P):
            self.close()
        elif key == Qt.Key_Space:
            self.main._toggle_pause()
        elif key == Qt.Key_F:
            self._go_fullscreen()
        else:
            super().keyPressEvent(event)

    def _restore_app(self) -> None:
        self.main.showNormal()
        self.main.raise_()
        self.main.activateWindow()
        self.close()

    def _go_fullscreen(self) -> None:
        self.close()
        self.main._toggle_fullscreen()

    def _on_player_state(self, state: str) -> None:
        if state == "playing":
            self.pp_btn.setIcon(make_icon("pause", 14, "white"))
        else:
            self.pp_btn.setIcon(make_icon("play", 14, "white"))

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.main.player.state_changed.disconnect(self._on_player_state)
        except (RuntimeError, TypeError):
            pass
        self.closed.emit()
        super().closeEvent(event)


class _AutoPlayNextBanner(QFrame):
    """Next episode auto-play countdown notification banner."""
    play_now_clicked = Signal()
    cancelled = Signal()

    def __init__(self, next_channel: Channel, countdown_sec: int = 10, parent=None) -> None:
        super().__init__(parent)
        self._countdown = countdown_sec
        self.setObjectName("autoPlayBanner")
        self.setStyleSheet(f"""
            QFrame#autoPlayBanner {{
                background: rgba(15, 17, 26, 240);
                border: 1px solid {COLORS['accent']};
                border-radius: 12px;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_icon("layers", 22, COLORS["accent"]).pixmap(22, 22))
        lay.addWidget(icon_lbl)

        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        self.count_lbl = QLabel(f"Playing next episode in {self._countdown}s...")
        self.count_lbl.setStyleSheet(f"color: {COLORS['muted']}; font-size: 9pt;")
        vbox.addWidget(self.count_lbl)

        ep_title = next_channel.name
        s = getattr(next_channel, "season", "")
        e = getattr(next_channel, "episode_num", "")
        if s and e:
            try:
                ep_title = f"S{int(s):02d}E{int(e):02d} — {ep_title}"
            except (ValueError, TypeError):
                ep_title = f"S{s}E{e} — {ep_title}"
        self.title_lbl = QLabel(ep_title)
        self.title_lbl.setStyleSheet("color: white; font-weight: 700; font-size: 11pt;")
        vbox.addWidget(self.title_lbl)
        lay.addLayout(vbox, 1)

        self.play_btn = QPushButton("Play Now")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: white;
                font-weight: 600;
                border-radius: 15px;
                padding: 6px 16px;
                border: none;
            }}
            QPushButton:hover {{
                background: {COLORS['accent2']};
            }}
        """)
        self.play_btn.clicked.connect(self.play_now_clicked.emit)
        lay.addWidget(self.play_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface']};
                color: {COLORS['text']};
                font-weight: 600;
                border-radius: 15px;
                padding: 6px 14px;
                border: 1px solid {COLORS['border']};
            }}
            QPushButton:hover {{
                background: {COLORS['surface2']};
                color: white;
            }}
        """)
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        lay.addWidget(self.cancel_btn)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self._timer.stop()
            self.play_now_clicked.emit()
        else:
            self.count_lbl.setText(f"Playing next episode in {self._countdown}s...")

    def stop(self) -> None:
        self._timer.stop()


class _FullscreenVideo(QDialog):
    """Fullscreen playback window with auto-hiding controls, back button, and transport bar."""

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(main_window, Qt.Window)
        self.main: MainWindow = main_window
        self.setWindowTitle("Nova IPTV - Now Playing")
        self.setStyleSheet("background-color: #000000;")
        self.setMouseTracking(True)

        self._is_dragging_seek = False
        self._current_dur_ms = 0
        self._auto_play_banner: _AutoPlayNextBanner | None = None
        self._auto_play_shown = False

        # Video surface (fills full dialog)
        self.video = VideoWidget(self, placeholder="")
        self.video.setMouseTracking(True)
        if hasattr(self.main, "thumb_video") and hasattr(self.main.thumb_video, "aspect_ratio"):
            self.video.set_aspect_ratio(self.main.thumb_video.aspect_ratio())
        self.video.installEventFilter(self)

        # On-screen toast display (for aspect ratio changes etc.)
        self._toast = QLabel("", self)
        self._toast.hide()
        self._toast.setStyleSheet(f"""
            background: rgba(15, 17, 26, 230);
            color: white;
            padding: 9px 20px;
            border-radius: 18px;
            font-weight: 700;
            font-size: 11pt;
            border: 1px solid {COLORS['accent']};
        """)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(1800)
        self._toast_timer.timeout.connect(self._toast.hide)

        # Build overlay bars
        self._build_top_bar()
        self._build_bottom_bar()

        # Inactivity auto-hide timer for overlays & cursor
        self._hide_timer = QTimer(self)
        self._hide_timer.setInterval(3500)
        self._hide_timer.timeout.connect(self._auto_hide_controls)

        # Connect player signals for live feedback in fullscreen
        self.main.player.state_changed.connect(self._on_player_state)
        self.main.player.position_changed.connect(self._on_position_changed)
        self.main.player.playback_finished.connect(self._on_playback_finished)

        # Initialize labels, states, and volumes
        self._update_channel_info()
        self._on_player_state(self.main._player_state)
        self._update_volume_ui()

        self.showFullScreen()
        self._show_controls()

    def _build_top_bar(self) -> None:
        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("fsTopBar")
        self.top_bar.setStyleSheet("""
            QWidget#fsTopBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(8, 10, 15, 230),
                    stop:0.65 rgba(8, 10, 15, 170),
                    stop:1 rgba(8, 10, 15, 0));
                border: none;
            }
        """)
        lay = QHBoxLayout(self.top_bar)
        lay.setContentsMargins(24, 16, 24, 20)
        lay.setSpacing(14)

        # Back button
        self.back_btn = QPushButton("  Back")
        self.back_btn.setObjectName("fsBackBtn")
        self.back_btn.setIcon(make_icon("back", 18, COLORS["text"]))
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setToolTip("Back to window (Esc)")
        self.back_btn.setStyleSheet(f"""
            QPushButton#fsBackBtn {{
                background: {COLORS["surface"]};
                color: {COLORS["text"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 19px;
                padding: 7px 18px;
                font-size: 11pt;
                font-weight: 600;
            }}
            QPushButton#fsBackBtn:hover {{
                background: {COLORS["surface2"]};
                border-color: {COLORS["accent"]};
                color: white;
            }}
        """)
        self.back_btn.clicked.connect(self.accept)
        lay.addWidget(self.back_btn)

        # Title & Subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #ffffff; font-size: 14pt; font-weight: 700;")
        title_box.addWidget(self.title_label)

        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10pt;")
        title_box.addWidget(self.sub_label)
        lay.addLayout(title_box)

        lay.addStretch(1)

        # Live pill badge
        self.live_badge = QLabel("● LIVE")
        self.live_badge.setStyleSheet(f"""
            background: rgba(239, 68, 68, 0.2);
            color: {COLORS['red']};
            border: 1px solid rgba(239, 68, 68, 0.5);
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 9pt;
            font-weight: 700;
        """)
        lay.addWidget(self.live_badge)

        # Exit fullscreen button
        self.close_fs_btn = self._fs_btn("compress", 18, "Exit Fullscreen (Esc)", self.accept)
        lay.addWidget(self.close_fs_btn)

    def _build_bottom_bar(self) -> None:
        self.bottom_bar = QWidget(self)
        self.bottom_bar.setObjectName("fsBottomBar")
        self.bottom_bar.setStyleSheet("""
            QWidget#fsBottomBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(8, 10, 15, 0),
                    stop:0.3 rgba(8, 10, 15, 180),
                    stop:1 rgba(8, 10, 15, 235));
                border: none;
            }
        """)
        lay = QVBoxLayout(self.bottom_bar)
        lay.setContentsMargins(28, 12, 28, 22)
        lay.setSpacing(10)

        # Progress / Seek row (for VOD / movies / series)
        self.seek_row = QWidget()
        seek_lay = QHBoxLayout(self.seek_row)
        seek_lay.setContentsMargins(0, 0, 0, 0)
        seek_lay.setSpacing(12)

        self.pos_label = QLabel("00:00")
        self.pos_label.setStyleSheet("color: #d1d5db; font-size: 10pt; font-family: monospace;")
        seek_lay.addWidget(self.pos_label)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        seek_lay.addWidget(self.seek_slider, 1)

        self.dur_label = QLabel("00:00")
        self.dur_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10pt; font-family: monospace;")
        seek_lay.addWidget(self.dur_label)

        lay.addWidget(self.seek_row)

        # Controls row
        ctrl_lay = QHBoxLayout()
        ctrl_lay.setSpacing(12)

        # Previous Channel
        self.prev_btn = self._fs_btn("prev", 18, "Previous Channel (Left Arrow)", self._on_prev)
        ctrl_lay.addWidget(self.prev_btn)

        # Play / Pause button
        self.pp_btn = QPushButton()
        self.pp_btn.setObjectName("fsPlayPauseBtn")
        self.pp_btn.setIcon(make_icon("pause", 22, "white"))
        self.pp_btn.setFixedSize(48, 48)
        self.pp_btn.setCursor(Qt.PointingHandCursor)
        self.pp_btn.setToolTip("Play / Pause (Space)")
        self.pp_btn.setStyleSheet(f"""
            QPushButton#fsPlayPauseBtn {{
                background: {COLORS["accent"]};
                border: none;
                border-radius: 24px;
            }}
            QPushButton#fsPlayPauseBtn:hover {{
                background: {COLORS["accent2"]};
            }}
        """)
        self.pp_btn.clicked.connect(self._on_play_pause)
        ctrl_lay.addWidget(self.pp_btn)

        # Next Channel
        self.next_btn = self._fs_btn("next", 18, "Next Channel (Right Arrow)", self._on_next)
        ctrl_lay.addWidget(self.next_btn)

        # Stop button
        self.stop_btn = self._fs_btn("stop", 16, "Stop Playback", self._on_stop)
        ctrl_lay.addWidget(self.stop_btn)

        ctrl_lay.addStretch(1)

        # Aspect Ratio button
        cur_asp = self.video.aspect_ratio().upper()
        self.aspect_btn = self._fs_btn("aspect", 18, f"Aspect Ratio: {cur_asp} (A)", self._toggle_aspect)
        ctrl_lay.addWidget(self.aspect_btn)

        # Audio & Subtitle Tracks button
        self.tracks_btn = self._fs_btn("subtitle", 18, "Audio & Subtitles (C / S)", self._show_tracks_menu)
        ctrl_lay.addWidget(self.tracks_btn)

        # Picture-in-Picture button
        self.pip_btn = self._fs_btn("pip", 18, "Picture-in-Picture (P)", self._on_pip)
        ctrl_lay.addWidget(self.pip_btn)

        # External Player button
        self.ext_btn = self._fs_btn("external", 18, "Open in External Player (E)", self._on_external)
        ctrl_lay.addWidget(self.ext_btn)

        ctrl_lay.addSpacing(6)

        # Volume control
        self.mute_btn = self._fs_btn("volume", 18, "Mute (M)", self._on_mute)
        ctrl_lay.addWidget(self.mute_btn)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 125)
        self.vol_slider.setValue(self.main.config.volume)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setCursor(Qt.PointingHandCursor)
        self.vol_slider.valueChanged.connect(self._on_vol_changed)
        ctrl_lay.addWidget(self.vol_slider)

        ctrl_lay.addSpacing(8)

        # Exit Fullscreen button
        self.exit_fs_btn = self._fs_btn("compress", 18, "Exit Fullscreen (Esc)", self.accept)
        ctrl_lay.addWidget(self.exit_fs_btn)

        lay.addLayout(ctrl_lay)

    def _fs_btn(self, icon: str, size: int, tooltip: str, slot) -> QPushButton:
        b = QPushButton()
        b.setObjectName("fsCtrlBtn")
        b.setIcon(make_icon(icon, size, COLORS["text"]))
        b.setFixedSize(38, 38)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tooltip)
        b.setStyleSheet(f"""
            QPushButton#fsCtrlBtn {{
                background: {COLORS["surface"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 19px;
            }}
            QPushButton#fsCtrlBtn:hover {{
                background: {COLORS["surface2"]};
                border-color: {COLORS["accent"]};
            }}
        """)
        b.clicked.connect(slot)
        return b

    def _toggle_aspect(self) -> None:
        modes = ["auto", "16:9", "4:3", "fill"]
        cur = self.video.aspect_ratio()
        nxt = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "auto"
        self.video.set_aspect_ratio(nxt)
        self.aspect_btn.setToolTip(f"Aspect Ratio: {nxt.upper()} (A)")
        self._show_toast(f"Aspect Ratio: {nxt.upper()}")

    def _show_toast(self, text: str) -> None:
        self._toast.setText(text)
        self._toast.adjustSize()
        self._toast.move((self.width() - self._toast.width()) // 2, self.height() - 130)
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start()

    def _show_tracks_menu(self) -> None:
        menu = QMenu(self)
        audio_tracks = self.main.player.audio_tracks()
        sub_tracks = self.main.player.subtitle_tracks()

        # Audio Tracks
        aud_label = menu.addAction("── Audio Tracks ──")
        aud_label.setEnabled(False)
        if not audio_tracks:
            no_aud = menu.addAction("Default Stream Audio")
            no_aud.setCheckable(True)
            no_aud.setChecked(True)
        else:
            cur_a = self.main.player.current_audio_track
            for t in audio_tracks:
                idx = t.get("index", 0)
                lang = (t.get("language") or "und").upper()
                codec = t.get("codec") or ""
                title = t.get("title") or f"Audio #{idx}"
                desc = f"{lang} • {title} ({codec})" if codec else f"{lang} • {title}"
                act = menu.addAction(desc)
                act.setCheckable(True)
                act.setChecked(idx == cur_a)
                act.triggered.connect(partial(self.main.player.set_audio_track, idx))

        menu.addSeparator()

        # Subtitles
        sub_label = menu.addAction("── Subtitles ──")
        sub_label.setEnabled(False)
        cur_s = self.main.player.current_subtitle_track
        off_act = menu.addAction("Off (Disabled)")
        off_act.setCheckable(True)
        off_act.setChecked(cur_s < 0)
        off_act.triggered.connect(lambda: self.main.player.set_subtitle_track(-1))

        for s in sub_tracks:
            idx = s.get("index", 0)
            lang = (s.get("language") or "und").upper()
            title = s.get("title") or f"Track #{idx}"
            act = menu.addAction(f"{lang} • {title}")
            act.setCheckable(True)
            act.setChecked(idx == cur_s)
            act.triggered.connect(partial(self.main.player.set_subtitle_track, idx))

        pt = self.tracks_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 6))
        menu.exec(pt)

    def _on_pip(self) -> None:
        self.accept()
        self.main._toggle_pip()

    def _on_external(self) -> None:
        self.main._launch_external()
        self.accept()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self.video.setGeometry(0, 0, w, h)
        top_h = max(70, self.top_bar.sizeHint().height())
        bot_h = max(90, self.bottom_bar.sizeHint().height())
        self.top_bar.setGeometry(0, 0, w, top_h)
        self.bottom_bar.setGeometry(0, h - bot_h, w, bot_h)
        self.top_bar.raise_()
        self.bottom_bar.raise_()
        if self._toast.isVisible():
            self._toast.move((w - self._toast.width()) // 2, h - 130)
            self._toast.raise_()
        if self._auto_play_banner and self._auto_play_banner.isVisible():
            self._auto_play_banner.move(w - 480, h - 140)
            self._auto_play_banner.raise_()

    def _show_controls(self) -> None:
        self.top_bar.show()
        self.bottom_bar.show()
        self.unsetCursor()
        self._hide_timer.start()

    def _auto_hide_controls(self) -> None:
        if self._is_dragging_seek:
            return
        if self.top_bar.underMouse() or self.bottom_bar.underMouse():
            return
        if self._auto_play_banner and self._auto_play_banner.underMouse():
            return
        self.top_bar.hide()
        self.bottom_bar.hide()
        self.setCursor(Qt.BlankCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        self._show_controls()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.video:
            if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress):
                self._show_controls()
            elif event.type() == QEvent.MouseButtonDblClick:
                self.accept()
                return True
        return super().eventFilter(obj, event)

    def _on_play_pause(self) -> None:
        self.main._toggle_pause()
        self._show_controls()

    def _on_prev(self) -> None:
        self.main._play_prev()
        self._update_channel_info()
        self._show_controls()

    def _on_next(self) -> None:
        self.main._play_next()
        self._update_channel_info()
        self._show_controls()

    def _on_stop(self) -> None:
        self.main.player.stop()
        self.accept()

    def _on_mute(self) -> None:
        self.main._toggle_mute()
        self._update_volume_ui()
        self._show_controls()

    def _on_vol_changed(self, val: int) -> None:
        self.main._on_volume(val)
        self._update_volume_ui()
        self._show_controls()

    def _update_volume_ui(self) -> None:
        muted = self.main._muted
        vol = self.main.config.volume
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(0 if muted else vol)
        self.vol_slider.blockSignals(False)
        self.mute_btn.setIcon(make_icon("mute" if (muted or vol == 0) else "volume", 18,
                                        COLORS["red"] if muted else COLORS["text"]))

    def _on_player_state(self, state: str) -> None:
        if state == "playing":
            self.pp_btn.setIcon(make_icon("pause", 22, "white"))
        else:
            self.pp_btn.setIcon(make_icon("play", 22, "white"))

    def _on_position_changed(self, pos_ms: int, dur_ms: int) -> None:
        self._current_dur_ms = dur_ms
        is_live = dur_ms <= 0
        self.live_badge.setVisible(is_live)
        self.seek_row.setVisible(not is_live)
        if not is_live and dur_ms > 0:
            if not self._is_dragging_seek:
                pct = int(min(1.0, max(0.0, pos_ms / dur_ms)) * 1000)
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(pct)
                self.seek_slider.blockSignals(False)
            self.pos_label.setText(self._format_time(pos_ms // 1000))
            self.dur_label.setText(self._format_time(dur_ms // 1000))

            # Auto-play next episode trigger at 95% progress
            if pos_ms >= dur_ms * 0.95 and not self._auto_play_shown:
                self._check_auto_play_next()

    def _on_playback_finished(self) -> None:
        if not self._auto_play_shown:
            self._check_auto_play_next()

    def _check_auto_play_next(self) -> None:
        ch = self.main._current_channel
        if ch is None or ch.kind != "series":
            return
        ctx = self.main._play_context
        idx = self.main._play_index
        if not ctx or idx + 1 >= len(ctx):
            return
        next_ep = ctx[idx + 1]
        self._auto_play_shown = True
        self._show_auto_play_banner(next_ep)

    def _show_auto_play_banner(self, next_channel: Channel) -> None:
        if self._auto_play_banner:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
        banner = _AutoPlayNextBanner(next_channel, 10, self)
        banner.setFixedWidth(460)
        banner.move(self.width() - 480, self.height() - 140)
        banner.play_now_clicked.connect(lambda: self._play_next_auto(next_channel))
        banner.cancelled.connect(self._cancel_auto_play)
        banner.show()
        banner.raise_()
        self._auto_play_banner = banner

    def _play_next_auto(self, next_channel: Channel) -> None:
        if self._auto_play_banner:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
            self._auto_play_banner = None
        self._auto_play_shown = False
        self.main.play_channel(next_channel, self.main._play_context)
        self._update_channel_info()

    def _cancel_auto_play(self) -> None:
        if self._auto_play_banner:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
            self._auto_play_banner = None

    def _on_seek_pressed(self) -> None:
        self._is_dragging_seek = True
        self._hide_timer.stop()

    def _on_seek_released(self) -> None:
        self._is_dragging_seek = False
        self._hide_timer.start()
        if self._current_dur_ms > 0:
            target_s = (self.seek_slider.value() / 1000.0) * (self._current_dur_ms / 1000.0)
            self.main.player.seek(target_s)

    @staticmethod
    def _format_time(seconds: int) -> str:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _update_channel_info(self) -> None:
        ch = self.main._current_channel
        if ch is not None:
            self.title_label.setText(ch.name)
            sub_parts = []
            if ch.display_group:
                sub_parts.append(ch.display_group)
            if ch.kind:
                sub_parts.append(ch.kind.title())
            if self.main.epg.loaded and ch.kind == "live":
                now, _ = self.main.epg.now_and_next(ch.tvg_id, ch.name)
                if now:
                    sub_parts.append(f"Now: {now.title}")
            self.sub_label.setText("  •  ".join(sub_parts))
            self.live_badge.setVisible(ch.kind == "live")
        else:
            self.title_label.setText("Now Playing")
            self.sub_label.setText("")
            self.live_badge.setVisible(False)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        self._show_controls()
        if key in (Qt.Key_Escape, Qt.Key_F, Qt.Key_Back):
            self.accept()
        elif key == Qt.Key_Space:
            self._on_play_pause()
        elif key == Qt.Key_A:
            self._toggle_aspect()
        elif key in (Qt.Key_C, Qt.Key_S):
            self._show_tracks_menu()
        elif key == Qt.Key_P:
            self._on_pip()
        elif key == Qt.Key_E:
            self._on_external()
        elif key == Qt.Key_Left:
            if self._current_dur_ms > 0:
                pos = self.main.player.position()
                self.main.player.seek(max(0.0, pos - 10.0))
            else:
                self._on_prev()
        elif key == Qt.Key_Right:
            if self._current_dur_ms > 0:
                pos = self.main.player.position()
                dur = self.main.player.duration() or (self._current_dur_ms / 1000.0)
                self.main.player.seek(min(dur, pos + 10.0))
            else:
                self._on_next()
        elif key == Qt.Key_Up:
            v = min(125, self.main.config.volume + 5)
            self._on_vol_changed(v)
        elif key == Qt.Key_Down:
            v = max(0, self.main.config.volume - 5)
            self._on_vol_changed(v)
        elif key == Qt.Key_M:
            self._on_mute()
        else:
            super().keyPressEvent(event)

    def done(self, r: int) -> None:
        self.unsetCursor()
        self._hide_timer.stop()
        if self._auto_play_banner:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
            self._auto_play_banner = None
        if hasattr(self.main, "thumb_video") and hasattr(self.main.thumb_video, "set_aspect_ratio"):
            self.main.thumb_video.set_aspect_ratio(self.video.aspect_ratio())
        try:
            self.main.player.state_changed.disconnect(self._on_player_state)
        except (RuntimeError, TypeError):
            pass
        try:
            self.main.player.position_changed.disconnect(self._on_position_changed)
        except (RuntimeError, TypeError):
            pass
        try:
            self.main.player.playback_finished.disconnect(self._on_playback_finished)
        except (RuntimeError, TypeError):
            pass
        super().done(r)


class _ConnectionDialog(QDialog):
    def __init__(self, profile: ProviderProfile | None, stats: dict,
                 expiry_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        if profile is None:
            form.addRow("Provider:", QLabel("Not configured"))
        else:
            form.addRow("Provider:", QLabel(profile.name))
            form.addRow("Type:", QLabel(
                "Xtream Codes" if profile.is_xtream() else "M3U Playlist"))
            form.addRow("Source:", QLabel(profile.redacted()))
            if profile.is_xtream() and expiry_text:
                form.addRow("Account expires:", QLabel(expiry_text))
        form.addRow("Channels loaded:", QLabel(str(stats.get("channels", 0))))
        ok = stats.get("channels", 0) > 0
        status = QLabel("Connected" if ok else "Offline")
        status.setStyleSheet(
            f"color: {COLORS['green'] if ok else COLORS['muted']}; font-weight: 600;")
        form.addRow("Status:", status)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class _DetailsDialog(QDialog):
    def __init__(self, channel: Channel,
                 now: EPGProgram | None, nxt: EPGProgram | None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(channel.name)
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        logo = LogoLabel(72)
        logo.load(channel.logo)
        top.addWidget(logo)
        info = QVBoxLayout()
        name = QLabel(channel.name)
        name.setObjectName("cardName")
        info.addWidget(name)
        info.addWidget(QLabel(f"{channel.display_group}  •  {channel.kind.title()}"))
        top.addLayout(info, 1)
        lay.addLayout(top)
        if now:
            lay.addWidget(QLabel(
                f"Now: {now.title} ({now.start.strftime('%H:%M')}–"
                f"{now.stop.strftime('%H:%M')})"))
        if nxt:
            lay.addWidget(QLabel(
                f"Next: {nxt.title} ({nxt.start.strftime('%H:%M')})"))
        lay.addWidget(QLabel(f"Stream URL: {channel.url}"))
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        watch = QPushButton("Watch")
        watch.setObjectName("primaryBtn")
        watch.clicked.connect(self.accept)
        buttons.addButton(watch, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


def _trailer_url(raw: str) -> str:
    """Normalize a youtube_trailer value to a watchable URL."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    if " " not in raw and len(raw) <= 20:  # probably a bare video id
        return f"https://www.youtube.com/watch?v={raw}"
    return raw


class _MovieDetailsDialog(QDialog):
    """Smarters-style movie details: poster, metadata, trailer, play."""

    play_requested = Signal(object)       # Channel (enriched when possible)
    fav_changed = Signal(object, bool)    # channel, new favorite state

    def __init__(self, channel: Channel, client: XtreamClient | None,
                 provider_id: str, is_fav: bool, parent=None) -> None:
        super().__init__(parent)
        self._channel = channel
        self._client = client
        self._provider_id = provider_id
        self._enriched: Channel | None = None
        self._fav = is_fav
        self._trailer = ""
        self._info_loader: _VodInfoLoader | None = None

        self.setWindowTitle(channel.name)
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(18)
        self.poster = LogoLabel(150)
        self.poster.load(channel.logo)
        top.addWidget(self.poster, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(6)
        self.f_title = QLabel(channel.name)
        self.f_title.setObjectName("dlgTitle")
        self.f_title.setWordWrap(True)
        info.addWidget(self.f_title)
        self.f_meta = QLabel("")
        self.f_meta.setObjectName("cardMeta")
        info.addWidget(self.f_meta)
        self.f_rating = QLabel("")
        self.f_rating.setObjectName("goldLabel")
        info.addWidget(self.f_rating)
        self.f_plot = QLabel("Loading details…")
        self.f_plot.setObjectName("plotLabel")
        self.f_plot.setWordWrap(True)
        info.addWidget(self.f_plot)
        self.f_cast = QLabel("")
        self.f_cast.setObjectName("cardMeta")
        self.f_cast.setWordWrap(True)
        info.addWidget(self.f_cast)
        self.f_director = QLabel("")
        self.f_director.setObjectName("cardMeta")
        self.f_director.setWordWrap(True)
        info.addWidget(self.f_director)
        info.addStretch(1)
        top.addLayout(info, 1)
        lay.addLayout(top)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.trailer_btn = QPushButton("  Watch trailer")
        self.trailer_btn.setObjectName("outlineBtn")
        self.trailer_btn.setIcon(make_icon("play", 14))
        self.trailer_btn.setCursor(Qt.PointingHandCursor)
        self.trailer_btn.clicked.connect(self._open_trailer)
        self.trailer_btn.hide()
        btn_row.addWidget(self.trailer_btn)
        btn_row.addStretch(1)
        self.fav_btn = QPushButton()
        self.fav_btn.setObjectName("outlineBtn")
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.clicked.connect(self._toggle_fav)
        self._refresh_fav_btn()
        btn_row.addWidget(self.fav_btn)
        self.play_btn = QPushButton("  Play")
        self.play_btn.setObjectName("primaryBtn")
        self.play_btn.setIcon(make_icon("play", 16, "white"))
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.clicked.connect(self._on_play)
        btn_row.addWidget(self.play_btn)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("outlineBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        # fill in what we already know; enrich via vod_info for Xtream
        self._fill_basic()
        if (self._client is not None and channel.stream_id
                and channel.kind == "movie"):
            self._info_loader = _VodInfoLoader(self._client,
                                               channel.stream_id)
            self._info_loader.finished_ok.connect(self._on_info)
            self._info_loader.failed.connect(self._on_info_failed)
            self._info_loader.start()
        else:
            self._fill_from_channel()

    # -- content -----------------------------------------------------------
    def _fill_basic(self) -> None:
        ch = self._channel
        meta = "  •  ".join(p for p in (ch.year, ch.genre, ch.duration) if p)
        self.f_meta.setText(meta or ch.display_group)

    def _fill_from_channel(self) -> None:
        """Show the channel's own metadata (M3U path / vod_info failed)."""
        ch = self._enriched or self._channel
        self.f_title.setText(ch.name)
        meta = "  •  ".join(p for p in (ch.year, ch.genre, ch.duration) if p)
        self.f_meta.setText(meta or ch.display_group)
        self.f_rating.setText(f"★ {ch.rating}" if ch.rating else "")
        self.f_plot.setText(ch.plot or "No synopsis available.")
        self.f_cast.setText(f"Cast: {ch.cast}" if ch.cast else "")
        self.f_director.setText(
            f"Director: {ch.director}" if ch.director else "")
        if ch.logo:
            self.poster.load(ch.logo)

    def _on_info(self, info: dict) -> None:
        self._enriched = xtream_vod_detail_to_channel(
            self._client, self._channel.stream_id, info, self._provider_id)
        self._trailer = _trailer_url(info.get("youtube_trailer", ""))
        self.trailer_btn.setVisible(bool(self._trailer))
        self._fill_from_channel()

    def _on_info_failed(self, msg: str) -> None:
        self._fill_from_channel()
        self.f_plot.setText(
            f"Could not load full details ({msg}).\n"
            "You can still play the movie.")

    # -- actions -------------------------------------------------------------
    def _refresh_fav_btn(self) -> None:
        self.fav_btn.setText(
            "  ★ Favorited" if self._fav else "  ☆ Add to favorites")
        self.fav_btn.setIcon(make_icon(
            "star" if self._fav else "star_outline", 14,
            "#fbbf24" if self._fav else COLORS["text"]))

    def _toggle_fav(self) -> None:
        self._fav = not self._fav
        self._refresh_fav_btn()
        self.fav_changed.emit(self._channel, self._fav)

    def _open_trailer(self) -> None:
        if self._trailer:
            QDesktopServices.openUrl(QUrl(self._trailer))

    def _on_play(self) -> None:
        self.play_requested.emit(self._enriched or self._channel)
        self.accept()


# -- main window ---------------------------------------------------------------

NAV_ITEMS = [
    ("home", "Home", "home"),
    ("live", "Live TV", "tv"),
    ("guide", "TV Guide", "calendar"),
    ("movie", "Movies", "film"),
    ("series", "TV Series", "layers"),
    ("catchup", "Catch-up", "replay"),
    ("favorites", "Favorites", "star"),
    ("history", "Recently Watched", "history"),
    ("playlists", "Providers", "list"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowTitle(f"{__app_name__} — IPTV Player")

        # responsive state (must exist before any resizeEvent can fire)
        self._panel_mode: str = "docked"   # or "drawer"
        self._sidebar_compact = False
        self._search_narrow = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._apply_breakpoints)
        self._page_anim = None

        self.resize(1440, 900)
        self.setMinimumSize(720, 500)

        self.config = AppConfig()
        self.favorites = FavoritesStore()
        self.epg = EPGManager()
        self.player = Player(self)
        self.parental = ParentalControls()
        self.resume = ResumeStore()

        # provider profiles (Smarters-Pro style); migrate legacy settings once
        migrate_legacy(self.config)
        self.profiles = ProfileStore()
        self._profile: ProviderProfile | None = self.profiles.active()
        self._xtream: XtreamClient | None = None
        self._xtream_user: dict = {}
        self._xloader: _XtreamLoader | None = None
        self._series_cache: dict[str, dict] = {}
        self._series_episodes: list[Channel] = []
        self._series_detail_id: str | None = None
        self._series_loader: _SeriesInfoLoader | None = None

        self.channels: list[Channel] = []
        self.history = HistoryStore()
        self._progress: dict[str, tuple[int, int]] = {}  # url -> (pos_ms, dur_ms)
        self._current_page = "home"
        self._current_kind: str | None = "live"
        self._current_category = ""
        self._context_lists: dict[str, list[Channel]] = {}
        self._play_context: list[Channel] = []
        self._play_index = -1
        self._current_channel: Channel | None = None
        self._loader: _PlaylistLoader | None = None
        self._epg_loader: _EpgLoader | None = None
        self._muted = False
        self._player_state = "stopped"
        self._count_labels: dict[str, QLabel] = {}
        self.category_boxes: dict[str, QComboBox] = {}
        self.grids: dict[str, ChannelGrid] = {}
        self._pip_window: _PipWindow | None = None
        self._auto_play_banner: _AutoPlayNextBanner | None = None
        self._auto_play_dismissed = False
        self._guide_start: datetime = datetime.now(timezone.utc).replace(
            minute=0 if datetime.now(timezone.utc).minute < 30 else 30,
            second=0, microsecond=0) - timedelta(minutes=30)
        # resume playback
        self._pending_resume_seek: float | None = None
        self._resume_seek_deadline = 0.0
        self._resume_timer = QTimer(self)
        self._resume_timer.setInterval(15000)
        self._resume_timer.timeout.connect(self._save_resume_point)
        self._resume_timer.start()
        # recording
        self._rec_started_at = 0.0
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._update_rec_elapsed)
        # search debouncer (smooth typing on large playlists)
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(220)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)
        self._np_slider_dragging = False

        self._build_ui()
        self._connect_player()
        self._build_login_overlay()
        self._refresh_home()

        geom = self.config.window_geometry
        if geom:
            self.restoreGeometry(geom)

        if self._profile is not None:
            self._load_profile(self._profile)
        elif self.config.playlist_source and not self.profiles.exists():
            # legacy fallback: no profiles file and migration found nothing
            self._load_playlist(self.config.playlist_source, silent=True)
            if self.config.epg_source:
                self._load_epg(self.config.epg_source, silent=True)
        else:
            self._show_login()
        if not Player.is_available():
            err = Player.import_error()
            QMessageBox.warning(
                self, "Player engine missing",
                "PyAV (the bundled FFmpeg decoder) could not be loaded.\n\n"
                "Install it with:  pip install av\n"
                "Then restart the app.\n\n"
                f"Details: {err}",
            )

    # -- UI construction ------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._topbar = self._build_titlebar()
        root.addWidget(self._topbar)

        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)
        self._mid_lay = mid
        self._sidebar = self._build_sidebar()

        self._content_wrap = QWidget()
        self._content_wrap.setObjectName("contentWrap")
        content_lay = QVBoxLayout(self._content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)
        self._account_banner = self._build_account_banner()
        self._account_banner.hide()
        content_lay.addWidget(self._account_banner)
        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        for key, _label, _icon in NAV_ITEMS:
            page = self._build_page(key)
            self._pages[key] = page
            self.stack.addWidget(page)
        content_lay.addWidget(self.stack, 1)
        content_lay.addWidget(self._build_statusbar())

        self._splitter = _SidebarSplitter(central)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._content_wrap)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.collapse_toggled.connect(self._toggle_sidebar_compact)
        self._splitter.splitterMoved.connect(self._on_sidebar_resized)

        init_w = max(180, min(420, self.config.sidebar_width or 212))
        self._splitter.setSizes([init_w, 1000])

        mid.addWidget(self._splitter, 1)

        self.right_panel = self._build_right_panel()
        mid.addWidget(self.right_panel)
        root.addLayout(mid, 1)


        self._nav_btns["home"].setChecked(True)

        # overlay layer: right-panel drawer, floating buttons, search popup
        self._drawer = Drawer(central, width=320)
        self._fab = QPushButton()
        self._fab.setObjectName("fabBtn")
        self._fab.setIcon(make_icon("play", 20, "white"))
        self._fab.setText("  Now Playing")
        self._fab.setFixedSize(160, 56)
        self._fab.setCursor(Qt.PointingHandCursor)
        self._fab.setParent(central)
        self._fab.clicked.connect(self._toggle_drawer)
        self._fab.hide()

        self._search_overlay = QFrame(central)
        self._search_overlay.setObjectName("searchOverlay")
        ov_lay = QVBoxLayout(self._search_overlay)
        ov_lay.setContentsMargins(14, 12, 14, 12)
        self._search_overlay.hide()

        self._apply_breakpoints()

    def _build_titlebar(self) -> QWidget:
        bar = _TitleBar()
        bar.setFixedHeight(56)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 8, 8)
        lay.setSpacing(10)

        self.conn_pill = StatPill()
        lay.addWidget(self.conn_pill)
        lay.addStretch(1)

        self.search = SearchBar()
        self.search.setFixedWidth(420)
        self.search.textChanged.connect(self._on_search_changed)
        self.search.returnPressed.connect(self._on_search_immediate)
        lay.addWidget(self.search)
        self._search_idx = lay.indexOf(self.search)
        self._search_btn = IconButton("search", 20)
        self._search_btn.setToolTip("Search")
        self._search_btn.clicked.connect(self._toggle_search_overlay)
        self._search_btn.hide()
        lay.addWidget(self._search_btn)
        lay.addStretch(1)

        help_btn = IconButton("help", 20)
        help_btn.setToolTip("Keyboard shortcuts (?)")
        help_btn.clicked.connect(self._show_shortcuts_dialog)
        lay.addWidget(help_btn)

        self.bell_btn = IconButton("bell", 20)
        self.bell_btn.setToolTip("Notifications")
        self.bell_btn.clicked.connect(self._show_notifications)
        lay.addWidget(self.bell_btn)

        gear = IconButton("gear", 20)
        gear.setToolTip("Settings")
        gear.clicked.connect(self._open_settings)
        lay.addWidget(gear)

        min_btn = WinButton("minus")
        min_btn.clicked.connect(self.showMinimized)
        lay.addWidget(min_btn)
        self.max_btn = WinButton("maximize")
        self.max_btn.clicked.connect(self._toggle_maximize)
        lay.addWidget(self.max_btn)
        close_btn = WinButton("close", danger=True)
        close_btn.clicked.connect(self.close)
        lay.addWidget(close_btn)
        return bar

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setIcon(make_icon("maximize", 14, COLORS["muted"]))
        else:
            self.showMaximized()
            self.max_btn.setIcon(make_icon("restore", 14, COLORS["muted"]))

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setMinimumWidth(64)
        side.setMaximumWidth(420)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 16, 14, 12)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(brand_pixmap(36))
        brand.addWidget(mark)
        title = QLabel("NOVA IPTV")
        title.setObjectName("brandTitle")
        self._brand_title = title
        brand.addWidget(title)
        brand.addStretch(1)

        self.side_toggle_btn = IconButton("sidebar", 18)
        self.side_toggle_btn.setToolTip("Collapse sidebar ([)")
        self.side_toggle_btn.clicked.connect(self._toggle_sidebar_compact)
        brand.addWidget(self.side_toggle_btn)

        lay.addLayout(brand)
        lay.addSpacing(10)


        # provider switcher (under the logo)
        self.provider_btn = QPushButton()
        self.provider_btn.setObjectName("providerBtn")
        self.provider_btn.setCursor(Qt.PointingHandCursor)
        self.provider_btn.setToolTip("Switch provider")
        self.provider_btn.clicked.connect(self._show_provider_menu)
        lay.addWidget(self.provider_btn)
        lay.addSpacing(10)
        self._refresh_provider_btn()

        self._nav_btns: dict[str, NavButton] = {}
        for key, label, icon in NAV_ITEMS:
            btn = NavButton(icon, label)
            btn.clicked.connect(partial(self._navigate, key))
            lay.addWidget(btn)
            self._nav_btns[key] = btn
        lay.addStretch(1)

        self._side_action_btns: list[NavButton] = []
        mgr = NavButton("folder", "Add provider")
        mgr.setCheckable(False)
        mgr.clicked.connect(self._show_login)
        lay.addWidget(mgr)
        self._side_action_btns.append(mgr)
        conn = NavButton("signal", "Connection")
        conn.setCheckable(False)
        conn.clicked.connect(self._open_connection)
        lay.addWidget(conn)
        self._side_action_btns.append(conn)
        lay.addSpacing(8)

        div = QWidget()
        div.setObjectName("sideDivider")
        lay.addWidget(div)
        lay.addSpacing(8)

        user = QHBoxLayout()
        user.setSpacing(10)
        av = QLabel()
        av.setPixmap(avatar_pixmap("Guest", 36))
        user.addWidget(av)
        name = QLabel("Guest")
        name.setObjectName("userName")
        self._user_name = name
        user.addWidget(name)
        user.addStretch(1)
        lay.addLayout(user)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("versionLabel")
        ver.setAlignment(Qt.AlignCenter)
        self._ver_label = ver
        lay.addWidget(ver)
        return side

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        self.status_text = ElidedLabel("Playlist: —")
        self.status_text.setObjectName("statusText")
        lay.addWidget(self.status_text)
        lay.addStretch(1)
        self.stream_dot = QLabel("●")
        self.stream_dot.setObjectName("statusDot")
        lay.addWidget(self.stream_dot)
        self.stream_label = QLabel("Stream status: Offline")
        self.stream_label.setObjectName("statusText")
        lay.addWidget(self.stream_label)
        return bar

    # -- account banner (inactive/expired Xtream account) -------------------
    def _build_account_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("accountBanner")
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(14, 8, 10, 8)
        lay.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(make_icon("bell", 18, COLORS["red"]).pixmap(18, 18))
        lay.addWidget(icon)
        self._banner_text = QLabel("")
        self._banner_text.setWordWrap(True)
        lay.addWidget(self._banner_text, 1)
        close = IconButton("close", 16)
        close.setToolTip("Dismiss")
        close.clicked.connect(self._hide_account_banner)
        lay.addWidget(close)
        return banner

    def _show_account_banner(self, message: str) -> None:
        self._banner_text.setText(message)
        self._account_banner.show()

    def _hide_account_banner(self) -> None:
        self._account_banner.hide()

    # -- login overlay ------------------------------------------------------
    def _build_login_overlay(self) -> None:
        central = self.centralWidget()
        self._login_overlay = QWidget(central)
        self._login_overlay.setObjectName("loginOverlay")
        lay = QVBoxLayout(self._login_overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        self._login_screen = LoginScreen(self.profiles, self._login_overlay)
        self._login_screen.authenticated.connect(self._on_authenticated)
        self._login_screen.back_btn.clicked.connect(self._hide_login)
        lay.addWidget(self._login_screen)
        self._login_overlay.hide()

    def _show_login(self) -> None:
        """Show the provider login screen over the main window."""
        self._login_screen.reset()
        self._login_screen.set_cancellable(self._profile is not None)
        central = self.centralWidget()
        if central is not None:
            self._login_overlay.setGeometry(central.rect())
        self._login_overlay.show()
        self._login_overlay.raise_()

    def _hide_login(self) -> None:
        if self._profile is None:
            return  # login is required; cannot dismiss
        self._login_overlay.hide()

    def _on_authenticated(self, profile: ProviderProfile) -> None:
        self._profile = profile
        self._hide_login()
        self._clear_content()
        self._refresh_provider_btn()
        self._navigate("home")
        self._load_profile(profile)

    # -- provider switcher --------------------------------------------------
    def _provider_expiry_text(self) -> str:
        if self._xtream is None:
            return ""
        exp = self._xtream.account_expiry()
        if exp is None:
            return "No expiry"
        return "Exp " + exp.strftime("%d %b %Y")

    def _refresh_provider_btn(self) -> None:
        p = self._profile
        if p is None:
            self.provider_btn.setText("No provider\nTap to add one")
            return
        if p.is_xtream():
            sub = f"Xtream • {self._provider_expiry_text() or '…'}"
        else:
            sub = "M3U Playlist"
        self.provider_btn.setText(f"{p.name}\n{sub}")

    def _show_provider_menu(self) -> None:
        menu = QMenu(self)
        header = menu.addAction("Providers")
        header.setEnabled(False)
        for p in self.profiles.all():
            act = menu.addAction(f"{p.name}  ({p.kind})")
            act.setCheckable(True)
            act.setChecked(self._profile is not None
                           and p.id == self._profile.id)
            act.triggered.connect(partial(self._switch_profile_by_id, p.id))
        menu.addSeparator()
        add_act = menu.addAction("Add provider…")
        add_act.triggered.connect(self._show_login)
        if self._profile is not None:
            rem_act = menu.addAction("Remove provider…")
            rem_act.triggered.connect(self._remove_provider)
        menu.exec(self.provider_btn.mapToGlobal(
            QPoint(0, self.provider_btn.height())))

    def _switch_profile_by_id(self, profile_id: str) -> None:
        if self._profile is not None and profile_id == self._profile.id:
            return
        profile = self.profiles.get(profile_id)
        if profile is None:
            return
        self._save_resume_point()
        if not self._confirm_stop_recording("switch provider"):
            return
        self.profiles.set_active(profile_id)
        self._profile = profile
        self.parental.lock_all()  # session unlocks don't cross providers
        self._clear_content()
        self._refresh_provider_btn()
        self._load_profile(profile)

    def _remove_provider(self) -> None:
        """Remove the active provider after confirmation."""
        p = self._profile
        if p is None:
            return
        answer = QMessageBox.question(
            self, "Remove provider",
            f"Remove the provider \"{p.name}\"?\n\n"
            "Its channels, movies and series will be unloaded and "
            "playback will stop. Your favorites are kept and will "
            "reappear if you add the provider again.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._save_resume_point()
        if not self._confirm_stop_recording("remove the provider"):
            return
        self.profiles.remove(p.id)
        self._profile = self.profiles.active()
        self.parental.lock_all()
        self._clear_content()
        self._refresh_provider_btn()
        if self._profile is not None:
            self._load_profile(self._profile)
        else:
            self._show_login()

    def _clear_content(self) -> None:
        """Unload everything (profile switch / provider removal)."""
        self._save_resume_point()
        self.player.stop()
        self.channels = []
        self.epg = EPGManager()
        self._xtream = None
        self._xtream_user = {}
        self._series_cache.clear()
        self._series_episodes = []
        self._series_detail_id = None
        self._play_context = []
        self._play_index = -1
        self._current_channel = None
        self.thumb_video.clear()
        self.np_title.setText("Nothing playing")
        self.np_meta.setText("")
        if hasattr(self, "np_seek_row"):
            self.np_seek_row.hide()
            self.np_time_now.setText("0:00")
            self.np_time_dur.setText("0:00")
            self.np_slider.setValue(0)
        self.pp_btn.setIcon(make_icon("play", 18))
        self._hide_account_banner()
        self._close_series_detail()
        self._update_now_next()
        self._update_status()
        self._update_bell()
        self._refresh_grid()
        self._refresh_home()
        if self._current_page == "playlists":
            self._refresh_providers_page()

    # -- responsive -----------------------------------------------------------
    # Breakpoints (window width):
    #   >= 1280 : full sidebar + docked right panel
    #   900-1279: 64px icon rail + right panel as overlay drawer (FAB toggle)
    #   < 900   : icon rail + stacked hero + search collapses to overlay field

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_overlays()
        if not self._resize_timer.isActive():
            self._resize_timer.start()

    def _layout_overlays(self) -> None:
        """Keep floating widgets positioned; called on every resize."""
        central = self.centralWidget()
        if central is None:
            return
        cw, ch = central.width(), central.height()
        if hasattr(self, "_fab") and self._fab.isVisible():
            self._fab.move(cw - 176, ch - 72)
            self._fab.raise_()
        if hasattr(self, "_drawer"):
            self._drawer.layout_host()
        if hasattr(self, "_search_overlay") and self._search_overlay.isVisible():
            self._position_search_overlay()
        if hasattr(self, "_login_overlay") and self._login_overlay.isVisible():
            self._login_overlay.setGeometry(central.rect())
        if hasattr(self, "_auto_play_banner") and self._auto_play_banner and self._auto_play_banner.isVisible():
            self._auto_play_banner.move(cw - 480, ch - 80)
            self._auto_play_banner.raise_()

    def _apply_breakpoints(self) -> None:
        w = self.width()
        # sidebar: if window is very narrow (<1000px), automatically compact to preserve room
        if w < 1000 and not self._sidebar_compact:
            self._apply_sidebar_compact(True, update_splitter=True)
        # right panel: docked vs drawer
        mode = "docked" if w >= 1280 else "drawer"
        if mode != self._panel_mode:
            self._panel_mode = mode
            self._apply_panel_mode()
        else:
            self._update_panel_visibility()
        # search: inline vs overlay icon button
        self._apply_search_mode(w < 900)
        # grids: cap columns on small windows
        for grid in self.grids.values():
            grid.set_max_columns(2 if w < 900 else 6)
        # hero orientation follows content width
        if hasattr(self, "hero"):
            self.hero.set_stacked(self.stack.width() < 1100)
        # search field width for the middle breakpoint
        if not self._search_narrow:
            self.search.setFixedWidth(260 if w < 1280 else 420)
        self._layout_overlays()

    def _toggle_sidebar_compact(self) -> None:
        self._apply_sidebar_compact(not self._sidebar_compact, update_splitter=True)

    def _on_sidebar_resized(self, pos: int, index: int) -> None:
        if index != 1:
            return
        sizes = self._splitter.sizes()
        if not sizes:
            return
        side_w = sizes[0]
        if side_w < 115:
            if not self._sidebar_compact:
                self._apply_sidebar_compact(True, update_splitter=False)
        else:
            if self._sidebar_compact:
                self._apply_sidebar_compact(False, update_splitter=False)
            self.config.sidebar_width = side_w

    def _apply_sidebar_compact(self, compact: bool, update_splitter: bool = True) -> None:
        if compact == self._sidebar_compact and not update_splitter:
            return
        self._sidebar_compact = compact
        for btn in list(self._nav_btns.values()) + self._side_action_btns:
            btn.set_compact(compact)
        lay = self._sidebar.layout()
        if compact:
            lay.setContentsMargins(9, 16, 9, 12)
        else:
            lay.setContentsMargins(14, 16, 14, 12)
        self._brand_title.setVisible(not compact)
        self._user_name.setVisible(not compact)
        self._ver_label.setVisible(not compact)
        self.provider_btn.setVisible(not compact)
        if hasattr(self, "side_toggle_btn"):
            self.side_toggle_btn.setToolTip(
                "Expand sidebar ([)" if compact else "Collapse sidebar ([)")
        if update_splitter and hasattr(self, "_splitter"):
            curr_sizes = self._splitter.sizes()
            tot = sum(curr_sizes) or 1200
            target_side = 64 if compact else max(180, min(380, self.config.sidebar_width or 212))
            self._splitter.setSizes([target_side, max(100, tot - target_side)])


    # -- right panel: docked vs drawer --------------------------------------
    def _apply_panel_mode(self) -> None:
        if self._panel_mode == "drawer":
            self._mid_lay.removeWidget(self.right_panel)
            self._drawer.set_content(self.right_panel)
            self._drawer.hide_now()
        else:
            taken = self._drawer.take_content()
            if taken is not None:
                self._mid_lay.addWidget(taken)
            self._drawer.hide_now()
        self._update_panel_visibility()

    def _update_panel_visibility(self) -> None:
        show = self._current_page in ("home", "live")
        if self._panel_mode == "docked":
            self.right_panel.setVisible(show)
        elif not show:
            self._drawer.hide()
        self._update_fab_visibility()

    def _update_fab_visibility(self) -> None:
        show = (self._panel_mode == "drawer"
                and self._current_page in ("home", "live"))
        self._fab.setVisible(show)
        if show:
            self._layout_overlays()

    def _toggle_drawer(self) -> None:
        if self._drawer.is_open():
            self._drawer.hide()
        else:
            self._drawer.show()

    # -- search overlay (<900px) -------------------------------------------
    def _apply_search_mode(self, narrow: bool) -> None:
        if narrow == self._search_narrow:
            return
        self._search_narrow = narrow
        if narrow:
            self._topbar.layout().removeWidget(self.search)
            self.search.hide()
            self._search_btn.show()
        else:
            self._close_search_overlay()
            self._topbar.layout().insertWidget(self._search_idx, self.search)
            self.search.show()
            self._search_btn.hide()

    def _toggle_search_overlay(self) -> None:
        if self._search_overlay.isVisible():
            self._close_search_overlay()
            return
        ov_lay = self._search_overlay.layout()
        if self.search.parent() is not self._search_overlay:
            ov_lay.addWidget(self.search)
        self.search.show()
        self._position_search_overlay()
        self._search_overlay.show()
        self._search_overlay.raise_()
        self.search.setFocus()

    def _position_search_overlay(self) -> None:
        bar = self._topbar
        w = 340
        x = max(8, bar.width() - w - 16)
        self._search_overlay.setGeometry(x, bar.height() + 6, w, 66)

    def _close_search_overlay(self) -> None:
        self._search_overlay.hide()

    # -- keyboard shortcuts ---------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if (hasattr(self, "_login_overlay")
                and self._login_overlay.isVisible()):
            # login screen owns the keyboard; only Esc (when cancellable)
            if key == Qt.Key_Escape:
                self._hide_login()
                event.accept()
            else:
                super().keyPressEvent(event)
            return
        if key == Qt.Key_Escape:
            if self._drawer.is_open():
                self._drawer.hide()
                event.accept()
                return
            if self._search_overlay.isVisible():
                self._close_search_overlay()
                event.accept()
                return
            super().keyPressEvent(event)
            return
        mods = event.modifiers()
        if (mods & Qt.ControlModifier and key == Qt.Key_K) or key == Qt.Key_Slash:
            if self._search_narrow and not self._search_overlay.isVisible():
                self._toggle_search_overlay()
            else:
                self.search.setFocus()
                self.search.selectAll()
            event.accept()
            return
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox, QSlider)):
            super().keyPressEvent(event)
            return
        if isinstance(focus, QAbstractButton) and key == Qt.Key_Space:
            super().keyPressEvent(event)  # let the button handle Space
            return
        handled = True
        if key == Qt.Key_Space:
            self._toggle_pause()
        elif key == Qt.Key_F:
            self._toggle_fullscreen()
        elif key == Qt.Key_P:
            self._toggle_pip()
        elif key == Qt.Key_A:
            self._on_toggle_aspect()
        elif key in (Qt.Key_C, Qt.Key_S):
            self._show_tracks_menu()
        elif key == Qt.Key_E:
            self._on_launch_external()
        elif key == Qt.Key_M:
            self._toggle_mute()
        elif key == Qt.Key_Left:
            self._play_prev()
        elif key == Qt.Key_Right:
            self._play_next()
        elif key == Qt.Key_Up:

            v = min(125, self.vol.value() + 5)
            self.vol.setValue(v)
            self._flash_status(f"Volume: {v}%", 1500)
        elif key == Qt.Key_Down:
            v = max(0, self.vol.value() - 5)
            self.vol.setValue(v)
            self._flash_status(f"Volume: {v}%", 1500)
        elif key == Qt.Key_BracketLeft:
            self._toggle_sidebar_compact()
        elif key in (Qt.Key_Question, Qt.Key_F1):
            self._show_shortcuts_dialog()

        else:
            handled = False
        if handled:
            event.accept()
        else:
            super().keyPressEvent(event)

    # -- pages ------------------------------------------------------------------
    def _build_page(self, key: str) -> QWidget:
        if key == "home":
            return self._build_home_page()
        if key == "series":
            return self._build_series_page()
        if key in ("live", "movie"):
            return self._build_grid_page(key)
        if key == "guide":
            return self._build_guide_page()
        if key == "catchup":
            return self._build_catchup_page()
        if key == "favorites":
            return self._build_grid_page(key)
        if key == "history":
            return self._build_history_page()
        if key == "playlists":
            return self._build_playlists_page()
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Unknown page"))
        return page

    # -- series browser (grid -> detail -> episodes) --------------------------
    def _build_series_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self.series_stack = QStackedWidget()
        lay.addWidget(self.series_stack)
        self.series_stack.addWidget(self._build_grid_page("series"))
        self.series_stack.addWidget(self._build_series_detail_page())
        return page

    def _build_series_detail_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(10)

        top = QHBoxLayout()
        back = QPushButton("  Back")
        back.setObjectName("outlineBtn")
        back.setIcon(make_icon("prev", 14))
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self._close_series_detail)
        top.addWidget(back)
        self.series_title = QLabel("")
        self.series_title.setObjectName("pageTitle")
        top.addWidget(self.series_title, 1)
        self.series_season_box = QComboBox()
        self.series_season_box.setMinimumWidth(160)
        self.series_season_box.currentIndexChanged.connect(
            self._on_season_changed)
        top.addWidget(self.series_season_box)
        lay.addLayout(top)

        info_row = QHBoxLayout()
        info_row.setSpacing(16)
        self.series_cover = LogoLabel(120)
        info_row.addWidget(self.series_cover, 0, Qt.AlignTop)
        info_txt = QVBoxLayout()
        info_txt.setSpacing(4)
        self.series_meta = QLabel("")
        self.series_meta.setObjectName("cardMeta")
        info_txt.addWidget(self.series_meta)
        self.series_plot = QLabel("")
        self.series_plot.setObjectName("plotLabel")
        self.series_plot.setWordWrap(True)
        info_txt.addWidget(self.series_plot)
        info_txt.addStretch(1)
        info_row.addLayout(info_txt, 1)
        lay.addLayout(info_row)

        self.series_loading = QLabel("Loading episodes…")
        self.series_loading.setObjectName("cardMeta")
        self.series_loading.hide()
        lay.addWidget(self.series_loading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)
        self._series_eps_inner = QWidget()
        self.series_eps_lay = QVBoxLayout(self._series_eps_inner)
        self.series_eps_lay.setSpacing(8)
        self.series_eps_lay.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self._series_eps_inner)
        return page

    def _open_series_detail(self, channel: Channel) -> None:
        """Smarters-style drill-down: series -> seasons -> episodes."""
        if not self._parental_allows(channel):
            return
        if self._xtream is None or not channel.series_id:
            self.play_channel(
                channel, self._context_lists.get("series", [channel]))
            return
        if self._current_page != "series":
            self._navigate("series")
        self._series_detail_id = channel.series_id
        self.series_title.setText(channel.name)
        self.series_cover.load(channel.logo)
        self.series_meta.setText("")
        self.series_plot.setText("")
        self._clear_layout(self.series_eps_lay)
        self.series_season_box.blockSignals(True)
        self.series_season_box.clear()
        self.series_season_box.blockSignals(False)
        self.series_stack.setCurrentIndex(1)
        self._load_series_info(channel.series_id)

    def _load_series_info(self, series_id: str) -> None:
        """Fetch (or reuse cached) series_info for the requested series."""
        cached = self._series_cache.get(series_id)
        if cached is not None:
            self._show_series_info(series_id, cached)
            return
        self.series_loading.show()
        if self._series_loader and self._series_loader.isRunning():
            return  # completion handler picks up the pending series id
        self._series_loader = _SeriesInfoLoader(
            self._xtream, series_id)
        self._series_loader.finished_ok.connect(self._on_series_info)
        self._series_loader.failed.connect(self._on_series_info_failed)
        self._series_loader.start()

    def _close_series_detail(self) -> None:
        if hasattr(self, "series_stack"):
            self.series_stack.setCurrentIndex(0)

    def _on_series_info(self, payload: dict) -> None:
        series_id = payload["series_id"]
        if series_id != self._series_detail_id:
            # a newer series was requested while this loaded; load it now
            if self._series_detail_id:
                self._load_series_info(self._series_detail_id)
            return
        info = payload["info"]
        self._series_cache[series_id] = info
        self._show_series_info(series_id, info)

    def _on_series_info_failed(self, msg: str) -> None:
        loader = self.sender()
        failed_id = getattr(loader, "series_id", None)
        if failed_id != self._series_detail_id:
            # stale failure; load whatever is currently requested
            if self._series_detail_id:
                self._load_series_info(self._series_detail_id)
            return
        self.series_loading.hide()
        self.series_plot.setText(f"Could not load episodes:\n{msg}")

    def _show_series_info(self, series_id: str, info: dict) -> None:
        self.series_loading.hide()
        name = info.get("name", "") or self.series_title.text()
        self.series_title.setText(name)
        meta = "  •  ".join(
            p for p in (info.get("genre", ""),
                        f"★ {info['rating']}" if info.get("rating") else "")
            if p)
        self.series_meta.setText(meta)
        self.series_plot.setText(info.get("plot", ""))
        if info.get("cover"):
            self.series_cover.load(info["cover"])
        seasons = info.get("seasons", {}) or {}
        nums = sorted(seasons,
                      key=lambda k: int(k) if str(k).isdigit() else 0)
        self.series_season_box.blockSignals(True)
        self.series_season_box.clear()
        for n in nums:
            count = len(seasons.get(n, []) or [])
            self.series_season_box.addItem(
                f"Season {n} ({count} episodes)", n)
        self.series_season_box.blockSignals(False)
        pid = self._profile.id if self._profile else ""
        self._series_episodes = xtream_episodes_to_channels(
            self._xtream, series_id, name, seasons, pid)
        self._render_episodes(nums[0] if nums else None)

    def _on_season_changed(self, index: int) -> None:
        if index < 0:
            return
        self._render_episodes(self.series_season_box.itemData(index))

    def _render_episodes(self, season_num) -> None:
        self._clear_layout(self.series_eps_lay)
        eps = [c for c in self._series_episodes
               if c.season == str(season_num)]
        if not eps:
            lbl = QLabel("No episodes found for this season.")
            lbl.setObjectName("cardMeta")
            self.series_eps_lay.addWidget(lbl)
        for ch in eps:
            row = _ClickableRow(ch)
            row.setObjectName("sideCard")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(14, 10, 14, 10)
            hl.setSpacing(12)
            badge = QLabel(f"E{ch.episode_num or '?'}")
            badge.setObjectName("upTime")
            badge.setFixedWidth(44)
            hl.addWidget(badge)
            txt = QVBoxLayout()
            txt.setSpacing(2)
            title = QLabel(ch.name)
            title.setObjectName("upTitle")
            title.setWordWrap(True)
            txt.addWidget(title)
            if ch.plot:
                plot = QLabel(ch.plot)
                plot.setObjectName("cardMeta")
                plot.setWordWrap(True)
                plot.setMaximumHeight(40)
                txt.addWidget(plot)
            hl.addLayout(txt, 1)
            if ch.duration:
                dur = QLabel(ch.duration)
                dur.setObjectName("cardMeta")
                hl.addWidget(dur)
            play = IconButton("play", 18)
            play.setToolTip("Play episode")
            hl.addWidget(play)
            season_eps = [e for e in self._series_episodes
                          if e.season == ch.season]

            def _play_episode(_payload=None, c=ch, ctx=season_eps):
                self.play_channel(c, ctx)

            row.clicked.connect(_play_episode)
            play.clicked.connect(lambda _=False: _play_episode())
            self.series_eps_lay.addWidget(row)
        self.series_eps_lay.addStretch(1)

    def _page_header(self, title: str) -> QHBoxLayout:
        lay = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        lay.addStretch(1)
        return lay

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(26, 18, 26, 26)
        lay.setSpacing(10)

        self.date_label = QLabel("")
        self.date_label.setObjectName("dateLabel")
        lay.addWidget(self.date_label)
        greet = QLabel(self._greeting())
        greet.setObjectName("greeting")
        lay.addWidget(greet)
        sub = QLabel("Your entertainment, all in one place.")
        sub.setObjectName("greetingSub")
        lay.addWidget(sub)
        lay.addSpacing(6)

        self.hero = HeroCard()
        self.hero.watch_clicked.connect(
            lambda ch: self.play_channel(ch, self._live_channels()))
        self.hero.details_clicked.connect(self._show_details)
        lay.addWidget(self.hero)

        sh_live = SectionHeader("Live Channels")
        sh_live.view_all.connect(partial(self._navigate, "live"))
        lay.addWidget(sh_live)
        self.home_live_scroll, self.home_live_row = self._hrow(236)
        lay.addWidget(self.home_live_scroll)

        sh_hist = SectionHeader("Continue Watching")
        sh_hist.view_all.connect(partial(self._navigate, "history"))
        lay.addWidget(sh_hist)
        self.home_hist_scroll, self.home_hist_row = self._hrow(300)
        lay.addWidget(self.home_hist_scroll)
        lay.addStretch(1)

        scroll.setWidget(inner)
        return page

    @staticmethod
    def _greeting() -> str:
        h = datetime.now().hour
        if h < 12:
            return "Good morning"
        if h < 18:
            return "Good afternoon"
        return "Good evening"

    def _hrow(self, height: int):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(height)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QHBoxLayout(inner)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(12)
        scroll.setWidget(inner)
        return scroll, lay

    def _clear_layout(self, lay) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_grid_page(self, key: str) -> QWidget:
        titles = {"live": "Live TV", "movie": "Movies",
                  "series": "TV Series", "favorites": "Favorites"}
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(10)
        head = self._page_header(titles[key])
        self._count_labels[key] = QLabel("")
        self._count_labels[key].setObjectName("cardMeta")
        head.addWidget(self._count_labels[key])
        if key in ("live", "movie", "series"):
            cat = QComboBox()
            cat.addItem("All categories")
            cat.currentTextChanged.connect(self._on_category_changed)
            head.addWidget(cat)
            self.category_boxes[key] = cat
        lay.addLayout(head)
        grid = ChannelGrid(columns=4)
        grid.channel_chosen.connect(partial(self._play_from, key))
        grid.fav_toggled.connect(self._on_fav_toggled)
        grid.channel_context_menu.connect(self._show_channel_context_menu)
        lay.addWidget(grid, 1)
        self.grids[key] = grid
        return page

    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel("TV Guide")
        title.setObjectName("pageTitle")
        header.addWidget(title)

        self.guide_category_box = QComboBox()
        self.guide_category_box.setObjectName("catBox")
        self.guide_category_box.addItem("All categories")
        self.guide_category_box.setMinimumWidth(160)
        self.guide_category_box.currentIndexChanged.connect(self._refresh_guide)
        header.addWidget(self.guide_category_box)

        header.addStretch(1)

        nav_prev = QPushButton("◀ −2h")
        nav_prev.setObjectName("outlineBtn")
        nav_prev.setCursor(Qt.PointingHandCursor)
        nav_prev.setToolTip("Scroll back 2 hours")
        nav_prev.clicked.connect(self._guide_prev_window)
        header.addWidget(nav_prev)

        nav_now = QPushButton("Now")
        nav_now.setObjectName("primaryBtn")
        nav_now.setCursor(Qt.PointingHandCursor)
        nav_now.setToolTip("Jump to current broadcast window")
        nav_now.clicked.connect(self._guide_jump_now)
        header.addWidget(nav_now)

        nav_next = QPushButton("+2h ▶")
        nav_next.setObjectName("outlineBtn")
        nav_next.setCursor(Qt.PointingHandCursor)
        nav_next.setToolTip("Scroll forward 2 hours")
        nav_next.clicked.connect(self._guide_next_window)
        header.addWidget(nav_next)

        self.guide_window_lbl = QLabel("")
        self.guide_window_lbl.setStyleSheet(f"color: {COLORS['muted']}; font-weight: 600; font-size: 10pt;")
        header.addWidget(self.guide_window_lbl)

        reload_btn = QPushButton("Reload guide")
        reload_btn.setObjectName("outlineBtn")
        reload_btn.setCursor(Qt.PointingHandCursor)
        reload_btn.clicked.connect(lambda: self._load_epg(self._guide_source()))
        header.addWidget(reload_btn)

        lay.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("guideScroll")
        scroll.setStyleSheet(f"""
            QScrollArea#guideScroll {{
                background: {COLORS['bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)
        lay.addWidget(scroll, 1)

        self.guide_inner = QWidget()
        self.guide_inner.setStyleSheet(f"background: {COLORS['bg']};")
        self.guide_lay = QVBoxLayout(self.guide_inner)
        self.guide_lay.setContentsMargins(8, 8, 8, 8)
        self.guide_lay.setSpacing(6)
        scroll.setWidget(self.guide_inner)
        return page

    def _guide_prev_window(self) -> None:
        self._guide_start -= timedelta(hours=2)
        self._refresh_guide()

    def _guide_jump_now(self) -> None:
        now = datetime.now(timezone.utc)
        self._guide_start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0) - timedelta(minutes=30)
        self._refresh_guide()

    def _guide_next_window(self) -> None:
        self._guide_start += timedelta(hours=2)
        self._refresh_guide()

    def _refresh_guide(self) -> None:
        if not hasattr(self, "guide_lay"):
            return
        self._clear_layout(self.guide_lay)

        if not self.epg.loaded:
            empty = EmptyState(
                "calendar", "No TV Guide Loaded",
                "Load an XMLTV guide to display timeline scheduling for Live TV.",
                "Load Guide")
            if empty.cta is not None:
                empty.cta.clicked.connect(lambda: self._load_epg(self._guide_source()))
            self.guide_lay.addWidget(empty)
            self.guide_lay.addStretch(1)
            return

        live_channels = self._live_channels()
        cur_cat = self.guide_category_box.currentText() if hasattr(self, "guide_category_box") else "All categories"
        if cur_cat and cur_cat != "All categories":
            live_channels = [c for c in live_channels if c.display_group == cur_cat]

        if not live_channels:
            empty = EmptyState("tv", "No channels found", "No live channels match the selected category.")
            self.guide_lay.addWidget(empty)
            self.guide_lay.addStretch(1)
            return

        guide_start = getattr(self, "_guide_start", None)
        if guide_start is None:
            now = datetime.now(timezone.utc)
            guide_start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0) - timedelta(minutes=30)
            self._guide_start = guide_start
        hours = 4
        guide_end = guide_start + timedelta(hours=hours)

        now = datetime.now(timezone.utc)
        if hasattr(self, "guide_window_lbl"):
            is_live_now = (guide_start <= now <= guide_end)
            live_prefix = f"<span style='color:{COLORS['red']}; font-weight:800;'>● LIVE NOW</span>&nbsp;&nbsp;•&nbsp;&nbsp;" if is_live_now else ""
            self.guide_window_lbl.setText(
                f"{live_prefix}{guide_start.strftime('%a, %b %d')} • {guide_start.strftime('%H:%M')} – {guide_end.strftime('%H:%M')}"
            )


        _PX_PER_MIN = 3.6
        total_mins = hours * 60
        timeline_width = int(total_mins * _PX_PER_MIN)

        # 1. Timeline Header Ruler (30-min marks)
        ruler_row = QFrame()
        ruler_row.setFixedHeight(34)
        ruler_row.setStyleSheet(f"background: {COLORS['surface2']}; border-radius: 6px;")
        rlay = QHBoxLayout(ruler_row)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)

        ch_col_hdr = QLabel("  Channels")
        ch_col_hdr.setFixedWidth(180)
        ch_col_hdr.setStyleSheet(f"color: {COLORS['muted']}; font-weight: 700; font-size: 9pt;")
        rlay.addWidget(ch_col_hdr)

        time_track = QWidget()
        time_track.setFixedWidth(timeline_width)
        time_track_lay = QHBoxLayout(time_track)
        time_track_lay.setContentsMargins(0, 0, 0, 0)
        time_track_lay.setSpacing(0)

        step_mins = 30
        for slot in range(0, total_mins, step_mins):
            slot_dt = guide_start + timedelta(minutes=slot)
            slot_lbl = QLabel(slot_dt.strftime("%H:%M"))
            slot_lbl.setFixedWidth(int(step_mins * _PX_PER_MIN))
            slot_lbl.setStyleSheet(f"color: {COLORS['text']}; font-size: 9pt; font-family: monospace; border-left: 1px solid {COLORS['border']}; padding-left: 4px;")
            time_track_lay.addWidget(slot_lbl)
        rlay.addWidget(time_track)
        rlay.addStretch(1)
        self.guide_lay.addWidget(ruler_row)

        now = datetime.now(timezone.utc)

        # 2. Channel rows (render up to 60 live channels for fluid scrolling)
        for ch in live_channels[:60]:
            row = QFrame()
            row.setObjectName("sideCard")
            row.setFixedHeight(54)
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(0)

            ch_badge = _ClickableRow(ch)
            ch_badge.setFixedWidth(180)
            ch_badge.setStyleSheet(f"border-right: 1px solid {COLORS['border']}; background: {COLORS['surface']}; padding: 4px 8px;")
            cblay = QHBoxLayout(ch_badge)
            cblay.setContentsMargins(8, 4, 8, 4)
            cblay.setSpacing(8)

            logo = LogoLabel(size=28)
            logo.load_url(ch.logo or "")
            cblay.addWidget(logo)

            ch_name = ElidedLabel(ch.name)
            ch_name.setStyleSheet("font-weight: 600; font-size: 9pt; color: white;")
            cblay.addWidget(ch_name, 1)

            ch_badge.clicked.connect(lambda c=ch: self.play_channel(c, self._live_channels()))
            row_lay.addWidget(ch_badge)

            prog_container = QWidget()
            prog_container.setFixedWidth(timeline_width)
            prog_lay = QHBoxLayout(prog_container)
            prog_lay.setContentsMargins(0, 2, 0, 2)
            prog_lay.setSpacing(2)

            progs = self.epg.guide_window(ch.tvg_id, ch.name, start=guide_start, hours=hours)
            if not progs:
                no_p = QLabel("No guide schedule available")
                no_p.setStyleSheet(f"color: {COLORS['muted']}; font-style: italic; font-size: 9pt; padding-left: 12px;")
                prog_lay.addWidget(no_p, 1)
            else:
                for pr in progs:
                    p_start = max(guide_start, pr.start)
                    p_stop = min(guide_end, pr.stop)
                    dur_secs = (p_stop - p_start).total_seconds()
                    if dur_secs <= 0:
                        continue
                    dur_mins = dur_secs / 60.0
                    card_w = max(40, int(dur_mins * _PX_PER_MIN) - 3)

                    p_btn = QPushButton()
                    p_btn.setCursor(Qt.PointingHandCursor)
                    p_btn.setFixedWidth(card_w)
                    p_btn.setFixedHeight(46)

                    is_current = (pr.start <= now < pr.stop)
                    is_past = (pr.stop <= now)

                    title_txt = pr.title
                    time_txt = f"{pr.start.strftime('%H:%M')}–{pr.stop.strftime('%H:%M')}"
                    p_btn.setText(f"{title_txt}\n{time_txt}")

                    if is_current:
                        p_btn.setStyleSheet(f"""
                            QPushButton {{
                                background: rgba(139, 92, 246, 0.25);
                                border: 1.5px solid {COLORS['accent']};
                                border-radius: 6px;
                                color: white;
                                font-size: 8.5pt;
                                font-weight: 600;
                                text-align: left;
                                padding: 3px 6px;
                            }}
                            QPushButton:hover {{
                                background: rgba(139, 92, 246, 0.45);
                            }}
                        """)
                    elif is_past:
                        p_btn.setStyleSheet(f"""
                            QPushButton {{
                                background: rgba(26, 30, 42, 0.6);
                                border: 1px solid {COLORS['border']};
                                border-radius: 6px;
                                color: {COLORS['muted']};
                                font-size: 8pt;
                                text-align: left;
                                padding: 3px 6px;
                            }}
                            QPushButton:hover {{
                                background: {COLORS['surface2']};
                                color: white;
                            }}
                        """)
                    else:
                        p_btn.setStyleSheet(f"""
                            QPushButton {{
                                background: {COLORS['surface']};
                                border: 1px solid {COLORS['border']};
                                border-radius: 6px;
                                color: {COLORS['text']};
                                font-size: 8.5pt;
                                text-align: left;
                                padding: 3px 6px;
                            }}
                            QPushButton:hover {{
                                background: {COLORS['surface2']};
                                border-color: {COLORS['accent']};
                                color: white;
                            }}
                        """)

                    p_btn.setToolTip(f"{pr.title}\n{time_txt}\n\n{pr.desc or 'No synopsis'}")
                    if is_current:
                        p_btn.clicked.connect(lambda _=False, c=ch: self.play_channel(c, self._live_channels()))
                    elif is_past and self._xtream and self._profile and self._profile.is_xtream() and getattr(ch, "stream_id", None):
                        p_btn.clicked.connect(partial(self._play_timeshift, ch, pr))
                    else:
                        p_btn.clicked.connect(partial(self._show_program_dialog, ch, pr))

                    prog_lay.addWidget(p_btn)
                prog_lay.addStretch(1)

            row_lay.addWidget(prog_container)
            row_lay.addStretch(1)
            self.guide_lay.addWidget(row)

        self.guide_lay.addStretch(1)

    def _show_program_dialog(self, channel: Channel, program: EPGProgram) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{program.title} — {channel.name}")
        dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)

        t_lbl = QLabel(program.title)
        t_lbl.setStyleSheet("color: white; font-size: 13pt; font-weight: 700;")
        lay.addWidget(t_lbl)

        time_lbl = QLabel(f"Airs: {program.start.strftime('%A, %b %d • %H:%M')} – {program.stop.strftime('%H:%M')}")
        time_lbl.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 600; font-size: 10pt;")
        lay.addWidget(time_lbl)

        ch_lbl = QLabel(f"Channel: {channel.name} ({channel.display_group})")
        ch_lbl.setStyleSheet(f"color: {COLORS['muted']}; font-size: 9.5pt;")
        lay.addWidget(ch_lbl)

        desc = QLabel(program.desc or "No program synopsis available.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['text']}; font-size: 10pt; line-height: 1.4;")
        lay.addWidget(desc)

        buttons = QDialogButtonBox()
        watch_btn = buttons.addButton("Watch Live Now", QDialogButtonBox.ActionRole)
        watch_btn.setStyleSheet(f"background: {COLORS['accent']}; color: white; border-radius: 4px; padding: 6px 14px;")
        watch_btn.clicked.connect(lambda: (dlg.accept(), self.play_channel(channel, self._live_channels())))
        close_btn = buttons.addButton(QDialogButtonBox.Close)
        close_btn.clicked.connect(dlg.reject)
        lay.addWidget(buttons)

        dlg.exec()

    def _build_catchup_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(10)
        head = self._page_header("Catch-up")
        sub = QLabel("Today's programmes from your TV guide")
        sub.setObjectName("cardMeta")
        head.addWidget(sub)
        head.addStretch(1)
        reload_btn = QPushButton("Reload guide")
        reload_btn.setObjectName("outlineBtn")
        reload_btn.clicked.connect(
            lambda: self._load_epg(self._guide_source()))
        head.addWidget(reload_btn)
        lay.addLayout(head)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)
        self.catchup_inner = QWidget()
        self.catchup_lay = QVBoxLayout(self.catchup_inner)
        self.catchup_lay.setSpacing(8)
        self.catchup_lay.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self.catchup_inner)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(10)
        lay.addLayout(self._page_header("Recently Watched"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)
        self.history_inner = QWidget()
        self.history_lay = QVBoxLayout(self.history_inner)
        self.history_lay.setSpacing(8)
        self.history_lay.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self.history_inner)
        return page

    def _build_playlists_page(self) -> QWidget:
        """Providers page (kept under the legacy 'playlists' nav key)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(12)
        lay.addLayout(self._page_header("Providers"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)
        self._providers_inner = QWidget()
        self._providers_lay = QVBoxLayout(self._providers_inner)
        self._providers_lay.setSpacing(10)
        self._providers_lay.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self._providers_inner)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        add_btn = QPushButton("  Add provider")
        add_btn.setObjectName("primaryBtn")
        add_btn.setIcon(make_icon("plus", 16, "white"))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._show_login)
        btn_row.addWidget(add_btn)
        self.remove_provider_btn = QPushButton("  Remove provider")
        self.remove_provider_btn.setObjectName("dangerBtn")
        self.remove_provider_btn.setIcon(
            make_icon("trash", 16, COLORS["red"]))
        self.remove_provider_btn.setCursor(Qt.PointingHandCursor)
        self.remove_provider_btn.clicked.connect(self._remove_provider)
        btn_row.addWidget(self.remove_provider_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        return page

    def _refresh_providers_page(self) -> None:
        self._clear_layout(self._providers_lay)
        profiles = self.profiles.all()
        active = self._profile
        if active is not None:
            card = QFrame()
            card.setObjectName("sideCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(20, 18, 20, 18)
            cl.setSpacing(6)
            title_row = QHBoxLayout()
            name = QLabel(active.name)
            name.setObjectName("sideTitle")
            title_row.addWidget(name)
            title_row.addStretch(1)
            badge = QLabel(
                "Xtream Codes" if active.is_xtream() else "M3U Playlist")
            badge.setObjectName("cardMeta")
            title_row.addWidget(badge)
            cl.addLayout(title_row)
            src = QLabel(active.redacted())
            src.setObjectName("cardMeta")
            src.setWordWrap(True)
            cl.addWidget(src)
            if active.is_xtream():
                exp = QLabel(f"Account expires: {self._provider_expiry_text()}")
                exp.setObjectName("cardMeta")
                cl.addWidget(exp)
            n_live = sum(1 for c in self.channels if c.kind == "live")
            n_mov = sum(1 for c in self.channels if c.kind == "movie")
            n_ser = sum(1 for c in self.channels if c.kind == "series")
            cl.addWidget(QLabel(
                f"{len(self.channels)} channels  •  {n_live} live  •  "
                f"{n_mov} movies  •  {n_ser} series"))
            guide = QLabel(
                f"Guide: {self._guide_source() or 'not configured'}")
            guide.setObjectName("cardMeta")
            guide.setWordWrap(True)
            cl.addWidget(guide)
            self._providers_lay.addWidget(card)

            others = [p for p in profiles if p.id != active.id]
            if others:
                sub = QLabel("Other providers")
                sub.setObjectName("sideTitle")
                self._providers_lay.addWidget(sub)
                for p in others:
                    row = QFrame()
                    row.setObjectName("sideCard")
                    hl = QHBoxLayout(row)
                    hl.setContentsMargins(14, 10, 14, 10)
                    lbl = QLabel(f"{p.name}")
                    lbl.setObjectName("upTitle")
                    hl.addWidget(lbl, 1)
                    kind = QLabel(p.kind)
                    kind.setObjectName("cardMeta")
                    hl.addWidget(kind)
                    switch = QPushButton("Switch")
                    switch.setObjectName("outlineBtn")
                    switch.setCursor(Qt.PointingHandCursor)
                    switch.clicked.connect(
                        partial(self._switch_profile_by_id, p.id))
                    hl.addWidget(switch)
                    self._providers_lay.addWidget(row)
        else:
            empty = EmptyState(
                "signal", "No provider configured",
                "Add an Xtream Codes login or an M3U playlist to start.",
                "Add provider")
            if empty.cta is not None:
                empty.cta.clicked.connect(self._show_login)
            self._providers_lay.addWidget(empty)
        self._providers_lay.addStretch(1)
        self.remove_provider_btn.setVisible(active is not None)

    # -- right panel ---------------------------------------------------------------
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPanel")
        panel.setFixedWidth(292)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 18, 16, 16)
        lay.setSpacing(10)

        np_head = QHBoxLayout()
        t = QLabel("Now Playing")
        t.setObjectName("sideTitle")
        np_head.addWidget(t)
        np_head.addStretch(1)
        self.np_visualizer = AudioVisualizer()
        self.np_visualizer.setToolTip("Audio Equalizer")
        np_head.addWidget(self.np_visualizer)
        lay.addLayout(np_head)


        card = QFrame()
        card.setObjectName("sideCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(8)
        self.thumb_video = VideoWidget(placeholder="Select a channel to play")
        self.thumb_video.setFixedHeight(150)
        self.thumb_video.mouseDoubleClickEvent = lambda _e: self._toggle_fullscreen()
        self.thumb_video.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumb_video.customContextMenuRequested.connect(self._show_video_context_menu)
        self.thumb_video.setCursor(Qt.PointingHandCursor)
        self.thumb_video.setToolTip("Double-click for fullscreen (or press F)")
        cl.addWidget(self.thumb_video)
        self.np_title = ElidedLabel("Nothing playing")
        self.np_title.setObjectName("cardName")
        self.np_title.setWordWrap(True)
        cl.addWidget(self.np_title)
        self.np_meta = QLabel("")
        self.np_meta.setObjectName("cardMeta")
        cl.addWidget(self.np_meta)

        # Mini seek row for VOD (movies/series)
        self.np_seek_row = QWidget()
        sl_lay = QVBoxLayout(self.np_seek_row)
        sl_lay.setContentsMargins(0, 4, 0, 0)
        sl_lay.setSpacing(4)
        time_row = QHBoxLayout()
        self.np_time_now = QLabel("0:00")
        self.np_time_now.setObjectName("cardMeta")
        self.np_time_dur = QLabel("0:00")
        self.np_time_dur.setObjectName("cardMeta")
        time_row.addWidget(self.np_time_now)
        time_row.addStretch(1)
        time_row.addWidget(self.np_time_dur)
        sl_lay.addLayout(time_row)

        self.np_slider = QSlider(Qt.Horizontal)
        self.np_slider.setObjectName("npSlider")
        self.np_slider.setRange(0, 1000)
        self.np_slider.setValue(0)
        self.np_slider.sliderPressed.connect(self._on_np_slider_pressed)
        self.np_slider.sliderReleased.connect(self._on_np_slider_released)
        self.np_slider.sliderMoved.connect(self._on_np_slider_moved)
        sl_lay.addWidget(self.np_slider)
        self.np_seek_row.hide()
        cl.addWidget(self.np_seek_row)

        self.rec_label = QLabel("")
        self.rec_label.setObjectName("recLabel")
        self.rec_label.setVisible(False)
        cl.addWidget(self.rec_label)
        lay.addWidget(card)

        transport = QHBoxLayout()
        transport.setSpacing(6)
        self.prev_btn = self._tbtn("prev", self._play_prev)
        self.pp_btn = self._tbtn("play", self._toggle_pause)
        self.next_btn = self._tbtn("next", self._play_next)
        self.rec_btn = self._tbtn("rec", self._toggle_record)
        self.rec_btn.setIcon(make_icon("rec", 14, COLORS["red"]))
        self.rec_btn.setToolTip("Record")
        self.rec_btn.setEnabled(False)
        self.aspect_btn = self._tbtn("aspect", self._on_toggle_aspect)
        self.aspect_btn.setToolTip("Aspect Ratio (Auto / 16:9 / 4:3 / Fill) (A)")
        self.tracks_btn = self._tbtn("subtitle", self._show_tracks_menu)
        self.tracks_btn.setToolTip("Audio & Subtitle Tracks (C / S)")
        self.ext_btn = self._tbtn("external", self._on_launch_external)
        self.ext_btn.setToolTip("Play in External Player (VLC / MPV) (E)")
        self.pip_btn = self._tbtn("pip", self._toggle_pip)
        self.pip_btn.setToolTip("Picture-in-Picture (P)")
        self.fs_btn = self._tbtn("expand", self._toggle_fullscreen)
        self.fs_btn.setToolTip("Fullscreen (F)")
        for b in (self.prev_btn, self.pp_btn, self.next_btn, self.rec_btn,
                  self.aspect_btn, self.tracks_btn, self.ext_btn, self.pip_btn):
            transport.addWidget(b)
        transport.addStretch(1)
        transport.addWidget(self.fs_btn)
        lay.addLayout(transport)

        vol_row = QHBoxLayout()
        self.mute_btn = IconButton("volume", 18)
        self.mute_btn.setIcon(make_icon("volume", 18, COLORS["muted"]))
        self.mute_btn.setToolTip("Mute")
        self.mute_btn.clicked.connect(self._toggle_mute)
        vol_row.addWidget(self.mute_btn)
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 125)
        self.vol.setValue(self.config.volume)
        self.vol.valueChanged.connect(self._on_volume)
        vol_row.addWidget(self.vol, 1)
        lay.addLayout(vol_row)

        epg_head = QHBoxLayout()
        epg_head.addWidget(QLabel("EPG"))
        epg_head.addStretch(1)
        self.epg_times = QLabel("")
        self.epg_times.setObjectName("upTime")
        epg_head.addWidget(self.epg_times)
        lay.addLayout(epg_head)
        self.epg_now = QLabel("No programme data")
        self.epg_now.setObjectName("upTitle")
        self.epg_now.setWordWrap(True)
        lay.addWidget(self.epg_now)
        self.epg_bar = QProgressBar()
        self.epg_bar.setObjectName("epgProgress")
        self.epg_bar.setRange(0, 100)
        self.epg_bar.setTextVisible(False)
        self.epg_bar.setFixedHeight(8)
        lay.addWidget(self.epg_bar)
        self.epg_next = QLabel("")
        self.epg_next.setObjectName("upChannel")
        self.epg_next.setWordWrap(True)
        lay.addWidget(self.epg_next)

        up_t = QLabel("Upcoming program")
        up_t.setObjectName("sideTitle")
        lay.addWidget(up_t)
        self.upcoming_box = QVBoxLayout()
        self.upcoming_box.setSpacing(6)
        lay.addLayout(self.upcoming_box)

        fav_t = QLabel("Favorite channels")
        fav_t.setObjectName("sideTitle")
        lay.addWidget(fav_t)
        self.fav_box = QVBoxLayout()
        self.fav_box.setSpacing(6)
        lay.addLayout(self.fav_box)

        lay.addStretch(1)
        return panel

    def _tbtn(self, icon: str, slot) -> QPushButton:
        b = QPushButton()
        b.setObjectName("transportBtn")
        b.setIcon(make_icon(icon, 18))
        b.setFixedSize(38, 38)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # -- wiring ----------------------------------------------------------------------
    def _connect_player(self) -> None:
        self.player.state_changed.connect(self._on_player_state)
        self.player.frame_ready.connect(self.thumb_video.set_frame)
        self.player.position_changed.connect(self._on_position)
        self.player.recording_started.connect(self._on_rec_started)
        self.player.recording_stopped.connect(self._on_rec_stopped)
        self.player.recording_error.connect(self._on_rec_error)
        self.player.playback_finished.connect(self._on_playback_finished)
        self.player.set_mute(self.config.muted)
        self.player.set_volume(self.config.volume)
        self.player.attach(self.thumb_video)
        self._update_mute_icon()

    # -- navigation -----------------------------------------------------------
    def _navigate(self, key: str) -> None:
        if key not in self._pages:
            return

        if self._current_page == key and self.stack.currentWidget() is self._pages[key]:
            return

        for k, btn in self._nav_btns.items():
            btn.setChecked(k == key)
        idx = [k for k, _l, _i in NAV_ITEMS].index(key)
        self.stack.setCurrentIndex(idx)
        self._current_page = key
        self._update_panel_visibility()
        if self._panel_mode == "drawer":
            self._drawer.hide()
        self._fade_page_in(self._pages[key])
        if key in self.category_boxes:
            cur_cat = self.category_boxes[key].currentText()
            self._current_category = "" if cur_cat == "All categories" else cur_cat
        else:
            self._current_category = ""
        if key in ("live", "movie"):
            self._current_kind = key
            self._refresh_grid()
        elif key == "series":
            self._current_kind = key
            self._close_series_detail()
            self._refresh_grid()
        elif key == "favorites":
            self._current_kind = None
            self._refresh_grid()
        elif key == "home":
            self._refresh_home()
        elif key == "guide":
            self._refresh_guide()
        elif key == "catchup":
            self._refresh_catchup()
        elif key == "history":
            self._refresh_history_page()
        elif key == "playlists":
            self._refresh_providers_page()

    def _fade_page_in(self, page: QWidget) -> None:
        """Subtle 180ms fade for page switches (skipped if reduced motion)."""
        if not animations_enabled():
            return
        try:
            eff = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(180)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.finished.connect(
                lambda: page.setGraphicsEffect(None))
            self._page_anim = anim  # keep alive
            anim.start(QAbstractAnimation.DeleteWhenStopped)
        except Exception:
            page.setGraphicsEffect(None)

    def _on_search_changed(self, text: str) -> None:
        if not text:
            self._search_timer.stop()
            self._run_search()
        else:
            self._search_timer.start()

    def _on_search_immediate(self) -> None:
        self._search_timer.stop()
        self._run_search()

    def _run_search(self) -> None:
        text = self.search.text()
        if self._current_page == "home" and text.strip():
            self._navigate("live")
            return
        if self._current_page in ("live", "movie", "series", "favorites"):
            self._refresh_grid()

    def _on_search(self, text: str) -> None:
        self._run_search()

    def _on_category_changed(self, text: str) -> None:
        group = "" if text == "All categories" else text
        if (group and self.parental.has_pin()
                and self.parental.is_locked(group)
                and not self.parental.is_unlocked(group)):
            dlg = PinDialog(self.parental.verify, self,
                            f'"{group}" is locked.')
            if dlg.exec() == QDialog.Accepted:
                self.parental.unlock_group(group)
                self._refresh_locks()
            else:
                box = self.sender()
                if isinstance(box, QComboBox):
                    box.blockSignals(True)
                    box.setCurrentText("All categories")
                    box.blockSignals(False)
                self._current_category = ""
                self._refresh_grid()
                return
        self._current_category = group
        self._refresh_grid()

    # -- profiles -----------------------------------------------------------
    def _load_profile(self, profile: ProviderProfile) -> None:
        if profile.is_xtream():
            self._load_xtream(profile)
        else:
            if profile.playlist_url:
                self._load_playlist(profile.playlist_url)
            if profile.epg_url:
                self._load_epg(profile.epg_url)

    def _load_xtream(self, profile: ProviderProfile) -> None:
        if self._xloader and self._xloader.isRunning():
            return
        self._show_loading_skeletons()
        self._xloader = _XtreamLoader(profile)
        self._xloader.finished_ok.connect(self._on_xtream_loaded)
        self._xloader.failed.connect(self._on_xtream_failed)
        self._xloader.start()

    def _on_xtream_failed(self, msg: str) -> None:
        QMessageBox.warning(
            self, "Provider failed",
            f"Could not load the Xtream provider:\n{msg}")

    def _on_xtream_loaded(self, payload: dict) -> None:
        self._xtream = payload["client"]
        self._xtream_user = payload.get("user_info", {}) or {}
        self._on_playlist_loaded(payload["channels"])
        epg_url = payload.get("epg_url", "")
        if epg_url:
            self._load_epg(epg_url)
        self._refresh_provider_btn()
        if not self._xtream.is_active():
            self._show_account_banner(
                "Your provider account is inactive or expired — "
                "streams may not play. Contact your provider.")
        else:
            self._hide_account_banner()

    def _guide_source(self) -> str:
        """XMLTV source for the active profile (auto for Xtream)."""
        if self._profile is None:
            return ""
        if self._profile.is_xtream():
            if self._xtream is not None:
                return self._xtream.xmltv_url()
            return ""
        return self._profile.epg_url

    # -- playlist -------------------------------------------------------------
    def _playlist_name(self) -> str:
        if self._profile is not None:
            return self._profile.name
        src = self.config.playlist_source
        if not src:
            return "—"
        if src.startswith("http"):
            return urlparse(src).hostname or "Remote playlist"
        return src.replace("\\", "/").split("/")[-1] or "Local playlist"

    def _open_add_dialog(self) -> None:
        dlg = AddPlaylistDialog(
            self.config.playlist_source, self.config.epg_source, self)
        if dlg.exec():
            src, epg_src = dlg.playlist_source(), dlg.epg_source()
            if src:
                self.config.playlist_source = src
                self.config.sync()
                self._load_playlist(src)
            if epg_src:
                self.config.epg_source = epg_src
                self.config.sync()
                self._load_epg(epg_src)

    def _open_connection(self) -> None:
        dlg = _ConnectionDialog(
            self._profile, {"channels": len(self.channels)},
            self._provider_expiry_text(), self)
        dlg.exec()

    def _load_playlist(self, source: str, silent: bool = False) -> None:
        if self._loader and self._loader.isRunning():
            return
        self._show_loading_skeletons()
        self._loader = _PlaylistLoader(source)
        self._loader.finished_ok.connect(self._on_playlist_loaded)
        self._loader.failed.connect(
            lambda msg: QMessageBox.warning(
                self, "Playlist failed",
                f"Could not load the playlist:\n{msg}"))
        self._loader.start()

    def _show_loading_skeletons(self) -> None:
        """Shimmer placeholders while the playlist loads."""
        for grid in self.grids.values():
            grid.show_skeletons(8)
        if hasattr(self, "home_live_row"):
            self._clear_layout(self.home_live_row)
            for _ in range(6):
                self.home_live_row.addWidget(
                    SkeletonCard(animate=animations_enabled()))
            self.home_live_row.addStretch(1)

    def _on_playlist_loaded(self, channels: list[Channel]) -> None:
        self.channels = channels
        for key, kind in (("live", "live"), ("movie", "movie"),
                          ("series", "series")):
            box = self.category_boxes[key]
            box.blockSignals(True)
            box.clear()
            box.addItem("All categories")
            box.addItems(categories(channels, kind))
            box.blockSignals(False)
        if hasattr(self, "guide_category_box"):
            self.guide_category_box.blockSignals(True)
            self.guide_category_box.clear()
            self.guide_category_box.addItem("All categories")
            self.guide_category_box.addItems(categories(channels, "live"))
            self.guide_category_box.blockSignals(False)
        self._current_category = ""
        self._update_status()
        self._refresh_grid()
        self._refresh_home()
        self._refresh_providers_page()
        self._refresh_locks()
        self._update_bell()

    # -- EPG ------------------------------------------------------------------
    def _load_epg(self, source: str, silent: bool = False) -> None:
        if not source:
            if not silent:
                QMessageBox.information(
                    self, "EPG",
                    "No guide configured for this provider. "
                    "Xtream providers load it automatically; for M3U, "
                    "add an XMLTV URL when creating the provider.")
            return
        if self._epg_loader and self._epg_loader.isRunning():
            return
        self._epg_loader = _EpgLoader(self.epg, source)
        self._epg_loader.finished_ok.connect(lambda _n: self._on_epg_loaded())
        self._epg_loader.failed.connect(
            lambda msg: QMessageBox.warning(
                self, "EPG failed", f"Could not load the guide:\n{msg}"))
        self._epg_loader.start()

    def _on_epg_loaded(self) -> None:
        self._refresh_grid()
        self._refresh_home()
        if self._current_page == "guide":
            self._refresh_guide()
        elif self._current_page == "catchup":
            self._refresh_catchup()
        self._update_now_next()
        self._update_bell()

    def _epg_label(self, ch: Channel) -> str:
        if not self.epg.loaded:
            return ch.display_group
        now, nxt = self.epg.now_and_next(ch.tvg_id, ch.name)
        parts = []
        if now:
            parts.append(f"{now.title} ({now.start.strftime('%H:%M')})")
        elif nxt:
            parts.append(f"Next: {nxt.title} ({nxt.start.strftime('%H:%M')})")
        return " · ".join(parts) if parts else ch.display_group

    # -- home -------------------------------------------------------------------
    def _live_channels(self) -> list[Channel]:
        return [c for c in self.channels if c.kind == "live"]

    def _refresh_home(self) -> None:
        self.date_label.setText(datetime.now().strftime("%A, %B %d"))
        # hero: last played else first live channel
        featured = None
        if self.config.last_channel_url:
            featured = next(
                (c for c in self.channels
                 if c.url == self.config.last_channel_url), None)
        if featured is None:
            live = self._live_channels()
            featured = live[0] if live else next(
                (c for c in self.channels if c.url), None)
        now = None
        if featured and self.epg.loaded:
            now, _ = self.epg.now_and_next(featured.tvg_id, featured.name)
        self.hero.set_feature(featured, now)

        # live row
        self._clear_layout(self.home_live_row)
        for ch in self._live_channels()[:12]:
            card = ChannelCard(ch, ch.url in self.favorites.all(),
                               self._epg_label(ch))
            card.clicked.connect(
                lambda c=ch: self.play_channel(c, self._live_channels()))
            card.fav_toggled.connect(self._on_fav_toggled)
            card.context_menu_requested.connect(self._show_channel_context_menu)
            card.set_locked(self._is_locked(ch))
            self.home_live_row.addWidget(card)
        self.home_live_row.addStretch(1)

        # continue watching
        self._clear_layout(self.home_hist_row)
        for entry in self.history.all()[:8]:
            ch = next((c for c in self.channels if c.url == entry.channel_url), None)
            if ch is None:
                ch = Channel(name=entry.channel_name, url=entry.channel_url)
            pos, dur = self._progress.get(entry.channel_url, (0, 0))
            pct = (pos / dur) if dur > 0 else 0.0
            played_str = entry.played_at.strftime("%H:%M")
            card = PosterCard(ch, pct, f"Watched {played_str}")
            card.clicked.connect(
                lambda c=ch: self.play_channel(c, [c]))
            self.home_hist_row.addWidget(card)
        self.home_hist_row.addStretch(1)

    # -- grids / search / favorites -------------------------------------------
    def _visible_channels(self) -> list[Channel]:
        if self._current_kind is None:  # favorites page
            favs = self.favorites.all()
            base = [c for c in self.channels if c.url in favs]
            return filter_channels(base, query=self.search.text())
        return filter_channels(
            self.channels,
            query=self.search.text(),
            category=self._current_category,
            kind=self._current_kind,
        )

    def _refresh_grid(self) -> None:
        if self._current_page not in ("live", "movie", "series", "favorites"):
            return
        key = self._current_page
        visible = self._visible_channels()
        self._context_lists[key] = visible
        query = self.search.text().strip()
        if key == "favorites" and not visible and not query:
            empty = dict(
                empty_title="No favorites yet",
                empty_sub="Tap the star on any channel to pin it here.",
                cta_text="Browse Live TV",
                cta_slot=partial(self._navigate, "live"))
        elif query and not visible:
            empty = dict(
                empty_title=f"No results for '{query}'",
                empty_sub="Try a different search term.",
                cta_text="Clear search",
                cta_slot=self.search.clear)
        elif not self.channels:
            empty = dict(
                empty_title="No provider yet",
                empty_sub="Add an Xtream Codes login or an M3U playlist "
                          "to start watching live TV, movies and series.",
                cta_text="Add provider",
                cta_slot=self._show_login)
        else:
            empty = dict(
                empty_title="Nothing here",
                empty_sub="No channels match the current filter.")
        self.grids[key].set_channels(
            visible, self.favorites.all(), self._epg_label, **empty)
        self._count_labels[key].setText(f"{len(self._context_lists[key])} items")
        self.grids[key].mark_selected(
            self._current_channel.url if self._current_channel else None)

    def _play_from(self, key: str, channel: Channel) -> None:
        # movies open the details dialog; xtream series drill into seasons
        if channel.kind == "movie":
            self._open_movie_details(channel)
            return
        if (channel.kind == "series"
                and channel.series_id and self._xtream is not None):
            self._open_series_detail(channel)
            return
        self.play_channel(channel, self._context_lists.get(key, [channel]))

    def _open_movie_details(self, channel: Channel) -> None:
        if not self._parental_allows(channel):
            return
        client = (self._xtream if self._profile is not None
                  and self._profile.is_xtream() else None)
        dlg = _MovieDetailsDialog(
            channel, client,
            self._profile.id if self._profile else "",
            channel.url in self.favorites.all(), self)
        dlg.play_requested.connect(
            lambda ch: self.play_channel(ch, [ch]))
        dlg.fav_changed.connect(self._on_fav_toggled)
        dlg.exec()

    def _on_fav_toggled(self, channel: Channel, state: bool) -> None:
        self.favorites.toggle(channel.url)
        for grid in self.grids.values():
            grid.update_favorite(channel.url, state)
        if self._current_page == "favorites":
            self._refresh_grid()
        self._refresh_fav_mini()

    def _show_shortcuts_dialog(self) -> None:
        dlg = ShortcutsDialog(self)
        dlg.exec()

    def _show_channel_context_menu(self, channel: Channel, pos: QPoint) -> None:
        menu = QMenu(self)

        play_act = menu.addAction(make_icon("play", 16), f"Play '{channel.name}'")
        play_act.triggered.connect(lambda: self.play_channel(channel, self._visible_channels()))

        pip_act = menu.addAction(make_icon("pip", 16), "Picture-in-Picture")
        pip_act.triggered.connect(lambda: (self.play_channel(channel, [channel]), self._toggle_pip()))

        ext_menu = menu.addMenu(make_icon("external", 16), "Play in External Player")
        ext_menu.addAction("Auto Detect / Default").triggered.connect(
            lambda: self._launch_external(channel, "auto"))
        detected = detect_players()
        for p_name in ("VLC", "MPV", "PotPlayer"):
            if p_name in detected:
                ext_menu.addAction(f"Launch with {p_name}").triggered.connect(
                    partial(self._launch_external, channel, p_name.lower()))

        menu.addSeparator()

        is_fav = channel.url in self.favorites.all()
        fav_icon = make_icon("star" if is_fav else "star_outline", 16,
                             COLORS["accent"] if is_fav else COLORS["text"])
        fav_text = "Remove from Favorites" if is_fav else "Add to Favorites"
        fav_act = menu.addAction(fav_icon, fav_text)
        fav_act.triggered.connect(lambda: self._on_fav_toggled(channel, not is_fav))

        menu.addSeparator()

        copy_url_act = menu.addAction(make_icon("list", 16), "Copy Stream URL")
        copy_url_act.triggered.connect(
            lambda: self._copy_to_clipboard(channel.url, "Stream URL copied to clipboard"))

        copy_name_act = menu.addAction(make_icon("tv", 16), "Copy Channel Name")
        copy_name_act.triggered.connect(
            lambda: self._copy_to_clipboard(channel.name, f"Copied '{channel.name}'"))

        if channel.kind == "movie":
            menu.addSeparator()
            details_act = menu.addAction(make_icon("film", 16), "Movie Details…")
            details_act.triggered.connect(lambda: self._open_movie_details(channel))
        elif channel.kind == "series" and channel.series_id:
            menu.addSeparator()
            series_act = menu.addAction(make_icon("layers", 16), "View Episodes…")
            series_act.triggered.connect(lambda: self._open_series_detail(channel))

        menu.exec(pos)

    def _copy_to_clipboard(self, text: str, msg: str) -> None:
        if text:
            cb = QGuiApplication.clipboard()
            if cb is not None:
                cb.setText(text)
            self._flash_status(msg, 3000)

    # -- catch-up -----------------------------------------------------------------
    def _catchup_empty(self, icon: str, title: str, sub: str,
                       cta_text: str = "", cta_slot=None) -> None:
        empty = EmptyState(icon, title, sub, cta_text)
        if empty.cta is not None and cta_slot is not None:
            empty.cta.clicked.connect(cta_slot)
        self.catchup_lay.addWidget(empty)
        self.catchup_lay.addStretch(1)

    def _refresh_catchup(self) -> None:
        self._clear_layout(self.catchup_lay)
        if not self.epg.loaded:
            self._catchup_empty(
                "tv", "No guide loaded",
                "Load a guide to see today's programmes.",
                "Load guide", lambda: self._load_epg(self._guide_source()))
            return
        live = self._live_channels()[:40]
        start_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0)
        items: list[tuple[datetime, EPGProgram, Channel]] = []
        for ch in live:
            for pr in self.epg.guide_window(ch.tvg_id, ch.name,
                                            start=start_day, hours=24):
                items.append((pr.start, pr, ch))
        items.sort(key=lambda t: t[0])
        if not items:
            self._catchup_empty(
                "search", "No programmes found",
                "No programmes found for today in the loaded guide.")
            return
        now = datetime.now(timezone.utc)
        for _start, pr, ch in items[:80]:
            row = QFrame()
            row.setObjectName("sideCard")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(14, 10, 14, 10)
            time_lbl = QLabel(
                f"{pr.start.strftime('%H:%M')}–{pr.stop.strftime('%H:%M')}")
            time_lbl.setObjectName("upTime")
            time_lbl.setFixedWidth(110)
            hl.addWidget(time_lbl)
            txt = QVBoxLayout()
            title = QLabel(pr.title)
            title.setObjectName("upTitle")
            title.setWordWrap(True)
            txt.addWidget(title)
            chan = QLabel(ch.name)
            chan.setObjectName("upChannel")
            txt.addWidget(chan)
            hl.addLayout(txt, 1)

            is_past = pr.stop <= now
            is_xtream_catchup = bool(
                self._xtream and self._profile and self._profile.is_xtream()
                and getattr(ch, "stream_id", None)
            )

            if is_past and is_xtream_catchup:
                watch = QPushButton("  Replay (Catch-up)")
                watch.setIcon(make_icon("replay", 14, COLORS["accent"]))
                watch.setObjectName("primaryBtn")
                watch.setCursor(Qt.PointingHandCursor)
                watch.clicked.connect(partial(self._play_timeshift, ch, pr))
            else:
                watch = QPushButton("Watch Live" if not is_past else "Watch Channel")
                watch.setObjectName("outlineBtn")
                watch.setCursor(Qt.PointingHandCursor)
                watch.clicked.connect(
                    lambda _=False, c=ch: self.play_channel(c, self._live_channels()))

            hl.addWidget(watch)
            self.catchup_lay.addWidget(row)
        self.catchup_lay.addStretch(1)

    def _play_timeshift(self, channel: Channel, program: EPGProgram) -> None:
        if not self._xtream or not getattr(channel, "stream_id", None):
            self._flash_status("Catch-up replay is not supported for this channel", 3000)
            return
        duration_min = max(1, int((program.stop - program.start).total_seconds() / 60))
        url = self._xtream.timeshift_url(channel.stream_id, program.start, duration_min)
        replay_channel = Channel(
            id=f"catchup_{channel.stream_id}_{int(program.start.timestamp())}",
            name=f"{channel.name} — {program.title} (Catch-up)",
            url=url,
            kind="movie",
            group=channel.group,
            logo=channel.logo,
            tvg_id=channel.tvg_id,
        )
        self.play_channel(replay_channel, [replay_channel])
        self._flash_status(f"Replaying Catch-up: {program.title}", 3500)

    # -- history page ---------------------------------------------------------------
    def _refresh_history_page(self) -> None:
        self._clear_layout(self.history_lay)
        entries = self.history.all()
        if not entries:
            empty = EmptyState(
                "history", "Nothing watched yet",
                "Play a channel and it will show up here.",
                "Browse Live TV")
            if empty.cta is not None:
                empty.cta.clicked.connect(partial(self._navigate, "live"))
            self.history_lay.addWidget(empty)
            self.history_lay.addStretch(1)
            return
        for entry in entries:
            ch = next((c for c in self.channels if c.url == entry.channel_url), None)
            if ch is None:
                ch = Channel(name=entry.channel_name, url=entry.channel_url)
            row = QFrame()
            row.setObjectName("sideCard")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(12, 8, 12, 8)
            art = QLabel()
            art.setPixmap(poster_pixmap(96, 64, entry.channel_name, entry.channel_url))
            hl.addWidget(art)
            txt = QVBoxLayout()
            title = QLabel(entry.channel_name)
            title.setObjectName("cardName")
            txt.addWidget(title)
            played_str = entry.played_at.strftime("%H:%M")
            txt.addWidget(QLabel(f"Watched {played_str}"))
            hl.addLayout(txt, 1)
            replay = QPushButton("Replay")
            replay.setObjectName("outlineBtn")
            replay.setCursor(Qt.PointingHandCursor)
            replay.clicked.connect(
                lambda _=False, c=ch: self.play_channel(c, [c]))
            hl.addWidget(replay)
            self.history_lay.addWidget(row)
        self.history_lay.addStretch(1)

    # -- playback ---------------------------------------------------------------
    def play_channel(self, channel: Channel,
                     context: list[Channel] | None = None) -> None:
        # parental gate: locked categories need the PIN first
        if not self._parental_allows(channel):
            return
        # don't clobber an active recording without asking
        if not self._confirm_stop_recording("switch channel"):
            return
        # remember where the outgoing VOD stopped
        self._save_resume_point()
        self._pending_resume_seek = None
        resume_pos = self._resume_offer(channel)
        if context is not None:
            self._play_context = list(context)
            try:
                self._play_index = self._play_context.index(channel)
            except ValueError:
                self._play_context = [channel]
                self._play_index = 0
        elif channel not in self._play_context:
            self._play_context = [channel]
            self._play_index = 0
        else:
            self._play_index = self._play_context.index(channel)
        self._current_channel = channel
        if hasattr(self, "_auto_play_banner") and self._auto_play_banner:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
            self._auto_play_banner = None
        self._auto_play_dismissed = False
        if self._pip_window is not None and hasattr(self._pip_window, "title_lbl"):
            self._pip_window.title_lbl.setText(channel.name)

        self.thumb_video.clear()
        if hasattr(self, "np_seek_row"):
            self.np_seek_row.hide()
            self.np_time_now.setText("0:00")
            self.np_time_dur.setText("0:00")
            self.np_slider.setValue(0)
        self.player.play(channel.url, channel.stream_headers)
        self.player.set_volume(self.vol.value())
        self.player.set_mute(self._muted)
        if resume_pos is not None:
            # seek once the engine is running; _on_position retries briefly
            self._pending_resume_seek = resume_pos
            self._resume_seek_deadline = time.monotonic() + 5.0

        self.np_title.setText(channel.name)
        self.np_meta.setText(
            f"{channel.display_group}  •  {channel.kind.title()}")
        for grid in self.grids.values():
            grid.mark_selected(channel.url)

        self.config.last_channel_url = channel.url
        self.config.sync()
        self.history.add(channel.name, channel.url)

        self._update_now_next()
        if self._current_page == "home":
            self._refresh_home()

    # -- parental controls ------------------------------------------------------
    def _is_locked(self, channel: Channel) -> bool:
        return (self.parental.has_pin()
                and self.parental.is_locked(channel.display_group))

    def _parental_allows(self, channel: Channel) -> bool:
        """True when the channel may play (PIN prompt for locked groups)."""
        if not self._is_locked(channel):
            return True
        if self.parental.is_unlocked(channel.display_group):
            return True
        dlg = PinDialog(self.parental.verify, self,
                        f'"{channel.display_group}" is locked.')
        if dlg.exec() == QDialog.Accepted:
            self.parental.unlock_group(channel.display_group)
            self._refresh_locks()
            return True
        return False

    def _refresh_locks(self) -> None:
        """Refresh lock badges after PIN / lock-list changes."""
        locked = (self.parental.locked_groups()
                  if self.parental.has_pin() else set())
        for grid in self.grids.values():
            grid.set_locked_groups(locked)

    # -- resume playback ----------------------------------------------------------
    def _save_resume_point(self) -> None:
        """Persist the current VOD position (called periodically + on stop)."""
        ch = self._current_channel
        if ch is None or ch.kind not in ("movie", "series") or not ch.url:
            return
        if self._player_state not in ("playing", "paused"):
            return
        pos = self.player.position()
        if pos > 5:  # ignore trivial positions near the start
            self.resume.save(ch.url, pos, self.player.duration() or 0.0)

    def _resume_offer(self, channel: Channel) -> float | None:
        """Offer to resume a partially-watched VOD. Returns position or None."""
        if channel.kind not in ("movie", "series") or not channel.url:
            return None
        entry = self.resume.position_for(channel.url)
        if entry is None:
            return None
        pos, dur = entry
        if not (dur > 0 and pos > 20 and pos < 0.95 * dur):
            return None
        box = QMessageBox(self)
        box.setWindowTitle("Resume playback")
        box.setText(f'Resume "{channel.name}" from {_fmt_time(pos)}?')
        resume_btn = box.addButton("Resume", QMessageBox.AcceptRole)
        box.addButton("Start over", QMessageBox.RejectRole)
        box.exec()
        return pos if box.clickedButton() == resume_btn else None

    # -- recording ------------------------------------------------------------------
    def _recordings_dir(self) -> Path:
        try:
            d = Path.home() / "Videos" / "NovaIPTV"
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            fallback = Path(QStandardPaths.writableLocation(
                QStandardPaths.AppDataLocation)) / "recordings"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def _toggle_record(self) -> None:
        if self.player.is_recording:
            self.player.stop_recording()
            return
        ch = self._current_channel
        if ch is None or self._player_state not in (
                "playing", "paused", "buffering"):
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(self._recordings_dir() / f"{_safe_filename(ch.name)}"
                   f"_{stamp}.mp4")
        self.player.start_recording(path)

    def _confirm_stop_recording(self, action: str) -> bool:
        """Ask before a recording is clobbered. Returns True to proceed."""
        if not self.player.is_recording:
            return True
        answer = QMessageBox.question(
            self, "Stop recording?",
            f"A recording is in progress. Stop it and {action}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.player.stop_recording()
            return True
        return False

    def _on_rec_started(self, path: str) -> None:
        self.rec_label.setVisible(True)
        self._rec_started_at = time.monotonic()
        self._update_rec_elapsed()
        self._rec_timer.start()
        self.rec_btn.setToolTip("Stop recording")
        self._flash_status(f"Recording — {Path(path).name}")

    def _on_rec_stopped(self, path: str) -> None:
        self._rec_timer.stop()
        self.rec_label.setVisible(False)
        self.rec_btn.setToolTip("Record")
        self._flash_status(f"Recording saved: {path}")

    def _on_rec_error(self, msg: str) -> None:
        self._rec_timer.stop()
        self.rec_label.setVisible(False)
        self.rec_btn.setToolTip("Record")
        QMessageBox.warning(self, "Recording", msg)

    def _update_rec_elapsed(self) -> None:
        elapsed = time.monotonic() - self._rec_started_at
        self.rec_label.setText(f"● REC  {_fmt_time(elapsed)}")

    def _flash_status(self, msg: str, ms: int = 6000) -> None:
        """Show a transient message in the status bar."""
        self.status_text.setText(msg)
        QTimer.singleShot(ms, self._update_status)

    def _play_prev(self) -> None:
        if not self._play_context:
            return
        self._play_index = (self._play_index - 1) % len(self._play_context)
        self.play_channel(self._play_context[self._play_index])

    def _play_next(self) -> None:
        if not self._play_context:
            return
        self._play_index = (self._play_index + 1) % len(self._play_context)
        self.play_channel(self._play_context[self._play_index])

    def _toggle_pause(self) -> None:
        self.player.toggle_pause()

    def _toggle_fullscreen(self) -> None:
        if self._pip_window is not None:
            self._pip_window.close()
        dlg = _FullscreenVideo(self)
        try:
            self.player.frame_ready.disconnect(self.thumb_video.set_frame)
        except (RuntimeError, TypeError):
            pass
        self.player.frame_ready.connect(dlg.video.set_frame)
        self.player.attach(dlg.video)
        dlg.exec()
        try:
            self.player.frame_ready.disconnect(dlg.video.set_frame)
        except (RuntimeError, TypeError):
            pass
        self.player.frame_ready.connect(self.thumb_video.set_frame)
        self.player.attach(self.thumb_video)
        self.thumb_video.set_aspect_ratio(dlg.video.aspect_ratio())

    def _toggle_pip(self) -> None:
        if self._pip_window is not None:
            self._pip_window.close()
            return
        if not self.player.current_url:
            self._flash_status("Nothing playing to show in Picture-in-Picture", 2500)
            return

        pip = _PipWindow(self)
        self._pip_window = pip
        pip.closed.connect(self._on_pip_closed)

        try:
            self.player.frame_ready.disconnect(self.thumb_video.set_frame)
        except (RuntimeError, TypeError):
            pass
        self.player.frame_ready.connect(pip.video.set_frame)
        self.player.attach(pip.video)

        screen = self.screen().availableGeometry()
        pip.move(screen.right() - pip.width() - 24, screen.bottom() - pip.height() - 32)
        pip.show()
        self._flash_status("Picture-in-Picture active (floating on top)", 3000)

    def _on_pip_closed(self) -> None:
        if self._pip_window is not None:
            try:
                self.player.frame_ready.disconnect(self._pip_window.video.set_frame)
            except (RuntimeError, TypeError):
                pass
            self.thumb_video.set_aspect_ratio(self._pip_window.video.aspect_ratio())
            self._pip_window = None

        self.player.frame_ready.connect(self.thumb_video.set_frame)
        self.player.attach(self.thumb_video)

    def _on_toggle_aspect(self) -> None:
        modes = ["auto", "16:9", "4:3", "fill"]
        cur = self.thumb_video.aspect_ratio()
        nxt = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "auto"
        self.thumb_video.set_aspect_ratio(nxt)
        if hasattr(self, "aspect_btn"):
            self.aspect_btn.setToolTip(f"Aspect Ratio: {nxt.upper()} (A)")
        self._flash_status(f"Aspect Ratio: {nxt.upper()}", 2000)

    def _show_tracks_menu(self) -> None:
        menu = QMenu(self)
        audio_tracks = self.player.audio_tracks()
        sub_tracks = self.player.subtitle_tracks()

        aud_label = menu.addAction("── Audio Tracks ──")
        aud_label.setEnabled(False)
        if not audio_tracks:
            no_aud = menu.addAction("Default Stream Audio")
            no_aud.setCheckable(True)
            no_aud.setChecked(True)
        else:
            cur_a = self.player.current_audio_track
            for t in audio_tracks:
                idx = t.get("index", 0)
                lang = (t.get("language") or "und").upper()
                codec = t.get("codec") or ""
                title = t.get("title") or f"Audio #{idx}"
                desc = f"{lang} • {title} ({codec})" if codec else f"{lang} • {title}"
                act = menu.addAction(desc)
                act.setCheckable(True)
                act.setChecked(idx == cur_a)
                act.triggered.connect(partial(self.player.set_audio_track, idx))

        menu.addSeparator()

        sub_label = menu.addAction("── Subtitles ──")
        sub_label.setEnabled(False)
        cur_s = self.player.current_subtitle_track
        off_act = menu.addAction("Off (Disabled)")
        off_act.setCheckable(True)
        off_act.setChecked(cur_s < 0)
        off_act.triggered.connect(lambda: self.player.set_subtitle_track(-1))

        for s in sub_tracks:
            idx = s.get("index", 0)
            lang = (s.get("language") or "und").upper()
            title = s.get("title") or f"Track #{idx}"
            act = menu.addAction(f"{lang} • {title}")
            act.setCheckable(True)
            act.setChecked(idx == cur_s)
            act.triggered.connect(partial(self.player.set_subtitle_track, idx))

        if hasattr(self, "tracks_btn"):
            pt = self.tracks_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 4))
            menu.exec(pt)
        else:
            menu.exec(self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2)))

    def _show_video_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)

        asp_menu = menu.addMenu(make_icon("aspect", 16), "Aspect Ratio")
        cur_mode = self.thumb_video.aspect_ratio()
        for mode, lbl in (("auto", "Auto (Fit)"), ("16:9", "16:9 (Widescreen)"),
                          ("4:3", "4:3 (Classic)"), ("fill", "Fill / Stretch")):
            act = asp_menu.addAction(lbl)
            act.setCheckable(True)
            act.setChecked(cur_mode == mode)
            act.triggered.connect(partial(self.thumb_video.set_aspect_ratio, mode))

        aud_menu = menu.addMenu("Audio Tracks")
        audio_tracks = self.player.audio_tracks()
        if not audio_tracks:
            no_a = aud_menu.addAction("Default Audio")
            no_a.setEnabled(False)
        else:
            cur_a = self.player.current_audio_track
            for t in audio_tracks:
                idx = t.get("index", 0)
                lang = (t.get("language") or "und").upper()
                act = aud_menu.addAction(f"{lang} - Track #{idx}")
                act.setCheckable(True)
                act.setChecked(idx == cur_a)
                act.triggered.connect(partial(self.player.set_audio_track, idx))

        sub_menu = menu.addMenu(make_icon("subtitle", 16), "Subtitles")
        cur_s = self.player.current_subtitle_track
        off_act = sub_menu.addAction("Off")
        off_act.setCheckable(True)
        off_act.setChecked(cur_s < 0)
        off_act.triggered.connect(lambda: self.player.set_subtitle_track(-1))
        for s in self.player.subtitle_tracks():
            idx = s.get("index", 0)
            lang = (s.get("language") or "und").upper()
            act = sub_menu.addAction(f"{lang} - Track #{idx}")
            act.setCheckable(True)
            act.setChecked(idx == cur_s)
            act.triggered.connect(partial(self.player.set_subtitle_track, idx))

        menu.addSeparator()

        pip_act = menu.addAction(make_icon("pip", 16), "Picture-in-Picture (P)")
        pip_act.triggered.connect(self._toggle_pip)

        ext_act = menu.addAction(make_icon("external", 16), "Play in External Player (VLC / MPV)")
        ext_act.triggered.connect(self._on_launch_external)

        fs_act = menu.addAction(make_icon("expand", 16), "Fullscreen (F)")
        fs_act.triggered.connect(self._toggle_fullscreen)

        menu.exec(self.thumb_video.mapToGlobal(pos))

    def _on_launch_external(self) -> None:
        self._launch_external(self._current_channel)

    def _launch_external(self, channel: Channel | None = None, choice: str = "auto") -> None:
        ch = channel or self._current_channel
        if not ch or not ch.url:
            self._flash_status("No stream available to launch externally", 2500)
            return
        ok, msg = launch_player(ch.url, ch.name, choice)
        if ok:
            self._flash_status(f"Launched in external player: {msg}", 3500)
        else:
            QMessageBox.information(
                self, "External Player",
                f"Could not launch stream in {choice}:\n{msg}\n\n"
                "Tip: Install VLC or MPV for native playback support."
            )

    def _on_volume(self, value: int) -> None:
        self.player.set_volume(value)
        self.config.volume = value

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self.player.set_mute(self._muted)
        self.config.muted = self._muted
        self.config.sync()
        self._update_mute_icon()

    def _update_mute_icon(self) -> None:
        self._muted = self.config.muted
        self.mute_btn.setIcon(make_icon(
            "mute" if self._muted else "volume", 18,
            COLORS["red"] if self._muted else COLORS["muted"]))
        self.mute_btn.setToolTip("Unmute" if self._muted else "Mute")

    def _on_np_slider_pressed(self) -> None:
        self._np_slider_dragging = True

    def _on_np_slider_moved(self, val: int) -> None:
        self.np_time_now.setText(_fmt_time(val))

    def _on_np_slider_released(self) -> None:
        self._np_slider_dragging = False
        target_s = float(self.np_slider.value())
        self.player.seek(target_s)

    def _on_position(self, pos_ms: int, dur_ms: int) -> None:
        if self._current_channel:
            self._progress[self._current_channel.url] = (pos_ms, dur_ms)
            is_vod = (self._current_channel.kind in ("movie", "series") or dur_ms > 0)
            if hasattr(self, "np_seek_row"):
                if is_vod and dur_ms > 0:
                    self.np_seek_row.show()
                    if not self._np_slider_dragging:
                        self.np_slider.blockSignals(True)
                        self.np_slider.setRange(0, max(1, dur_ms // 1000))
                        self.np_slider.setValue(pos_ms // 1000)
                        self.np_slider.blockSignals(False)
                        self.np_time_now.setText(_fmt_time(pos_ms / 1000))
                        self.np_time_dur.setText(_fmt_time(dur_ms / 1000))
                else:
                    self.np_seek_row.hide()

            # auto-play next episode trigger at >= 95%
            if (self._current_channel.kind == "series"
                    and dur_ms > 0 and pos_ms >= dur_ms * 0.95
                    and not self._auto_play_dismissed and self._auto_play_banner is None):
                if self._play_context and self._play_index + 1 < len(self._play_context):
                    self._show_auto_play_next(self._play_context[self._play_index + 1])

        # resume-seek: the engine may need a moment before seek() works;
        # retry on each position report for ~5 s, then play from the start.
        if self._pending_resume_seek is not None:
            if time.monotonic() < self._resume_seek_deadline:
                if self.player.seek(self._pending_resume_seek):
                    self._pending_resume_seek = None
            else:
                self._pending_resume_seek = None

    def _on_playback_finished(self) -> None:
        """Natural end of a stream: a finished VOD needs no resume point."""
        ch = self._current_channel
        if ch is not None and ch.kind in ("movie", "series") and ch.url:
            self.resume.clear(ch.url)
        if (ch is not None and ch.kind == "series"
                and not self._auto_play_dismissed and self._auto_play_banner is None):
            if self._play_context and self._play_index + 1 < len(self._play_context):
                self._show_auto_play_next(self._play_context[self._play_index + 1])

    def _show_auto_play_next(self, next_ch: Channel) -> None:
        if self._auto_play_banner is not None:
            return
        banner = _AutoPlayNextBanner(next_ch, 10, self)
        banner.setFixedWidth(460)
        cw, ch = self.width(), self.height()
        banner.move(cw - 480, ch - banner.sizeHint().height() - 40)
        banner.play_now_clicked.connect(lambda: self._play_auto_next(next_ch))
        banner.cancelled.connect(self._cancel_auto_next)
        banner.show()
        banner.raise_()
        self._auto_play_banner = banner

    def _play_auto_next(self, next_ch: Channel) -> None:
        if self._auto_play_banner is not None:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
            self._auto_play_banner = None
        self.play_channel(next_ch, self._play_context)

    def _cancel_auto_next(self) -> None:
        if self._auto_play_banner is not None:
            self._auto_play_banner.stop()
            self._auto_play_banner.deleteLater()
            self._auto_play_banner = None
        self._auto_play_dismissed = True

    def _on_player_state(self, state: str) -> None:
        self._player_state = state
        if hasattr(self, "np_visualizer"):
            self.np_visualizer.set_active(state == "playing")
        if state == "playing":
            self.pp_btn.setIcon(make_icon("pause", 18))

        elif state == "paused":
            self.pp_btn.setIcon(make_icon("play", 18))
        elif state in ("stopped", "error"):
            self.pp_btn.setIcon(make_icon("play", 18))
            if hasattr(self, "np_seek_row"):
                self.np_seek_row.hide()
                self.np_time_now.setText("0:00")
                self.np_time_dur.setText("0:00")
                self.np_slider.setValue(0)
        self.rec_btn.setEnabled(
            state in ("playing", "paused", "buffering")
            and self._current_channel is not None)
        if state == "stopped" and self._current_channel is not None:
            # A stop at >=95% means "watched": drop the resume point.
            ch = self._current_channel
            if ch.kind in ("movie", "series") and ch.url:
                entry = self.resume.position_for(ch.url)
                if entry is not None:
                    pos, dur = entry
                    if dur > 0 and pos >= 0.95 * dur:
                        self.resume.clear(ch.url)
        if state == "error":
            detail = (self.player.last_error or "").strip()
            msg = ("The built-in player could not play this stream.\n"
                   "It may be offline, geo-blocked, use an unsupported codec, "
                   "or the playlist URL expired.")
            if detail:
                msg += f"\n\nDetails: {detail}"
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Playback error")
            box.setText(msg)
            launch_btn = box.addButton("Launch in External Player (VLC / MPV)", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Close)
            box.exec()
            if box.clickedButton() == launch_btn:
                self._launch_external()

    # -- now playing panel ----------------------------------------------------------
    def _update_now_next(self) -> None:
        ch = self._current_channel
        if ch is None or not self.epg.loaded:
            self.epg_now.setText("No programme data")
            self.epg_next.setText("")
            self.epg_times.setText("")
            self.epg_bar.setValue(0)
            self.upcoming_box_update(None)
            return
        now, nxt = self.epg.now_and_next(ch.tvg_id, ch.name)
        if now:
            self.epg_now.setText(now.title)
            total = (now.stop - now.start).total_seconds()
            elapsed = (datetime.now(timezone.utc) - now.start).total_seconds()
            pct = max(0, min(100, int(elapsed / total * 100))) if total > 0 else 0
            self.epg_bar.setValue(pct)
            self.epg_times.setText(
                f"{now.start.strftime('%H:%M')} – {now.stop.strftime('%H:%M')}")
        else:
            self.epg_now.setText("No programme data")
            self.epg_bar.setValue(0)
            self.epg_times.setText("")
        if nxt:
            self.epg_next.setText(
                f"Next: {nxt.title} ({nxt.start.strftime('%H:%M')})")
        else:
            self.epg_next.setText("")
        self.upcoming_box_update(ch)

    def upcoming_box_update(self, ch: Channel | None) -> None:
        self._clear_layout(self.upcoming_box)
        if ch is None or not self.epg.loaded:
            lbl = QLabel("Guide not loaded")
            lbl.setObjectName("upChannel")
            self.upcoming_box.addWidget(lbl)
            return
        progs = self.epg.programs_for(ch.tvg_id, ch.name)
        now_utc = datetime.now(timezone.utc)
        future = [pr for pr in progs if pr.start > now_utc][:3]
        if not future:
            lbl = QLabel("No upcoming programmes")
            lbl.setObjectName("upChannel")
            self.upcoming_box.addWidget(lbl)
            return
        for pr in future:
            row = _ClickableRow(ch)
            row.setObjectName("sideCard")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 8, 10, 8)
            t = QLabel(pr.start.strftime("%H:%M"))
            t.setObjectName("upTime")
            t.setFixedWidth(44)
            hl.addWidget(t)
            txt = QVBoxLayout()
            title = QLabel(pr.title)
            title.setObjectName("upTitle")
            title.setWordWrap(True)
            txt.addWidget(title)
            txt.addWidget(QLabel(ch.name))
            txt.itemAt(1).widget().setObjectName("upChannel")
            hl.addLayout(txt, 1)
            row.clicked.connect(
                lambda c=ch: self.play_channel(c, self._play_context or [c]))
            self.upcoming_box.addWidget(row)

    def _refresh_fav_mini(self) -> None:
        self._clear_layout(self.fav_box)
        favs = [c for c in self.channels if c.url in self.favorites.all()][:5]
        if not favs:
            lbl = QLabel("Star channels to pin them here")
            lbl.setObjectName("upChannel")
            self.fav_box.addWidget(lbl)
            return
        for ch in favs:
            row = _ClickableRow(ch)
            hl = QHBoxLayout(row)
            hl.setContentsMargins(4, 4, 4, 4)
            logo = LogoLabel(36)
            logo.load(ch.logo)
            hl.addWidget(logo)
            name = QLabel(ch.name)
            name.setObjectName("upTitle")
            name.setWordWrap(True)
            hl.addWidget(name, 1)
            row.clicked.connect(
                lambda c=ch: self.play_channel(c, self._play_context or [c]))
            self.fav_box.addWidget(row)

    # -- notifications ------------------------------------------------------------
    def _upcoming_soon(self) -> list[tuple[datetime, str, Channel]]:
        if not self.epg.loaded:
            return []
        now_utc = datetime.now(timezone.utc)
        out = []
        for ch in self._live_channels()[:25]:
            _now, nxt = self.epg.now_and_next(ch.tvg_id, ch.name)
            if nxt and 0 <= (nxt.start - now_utc).total_seconds() <= 5400:
                out.append((nxt.start, nxt.title, ch))
        out.sort(key=lambda t: t[0])
        return out

    def _update_bell(self) -> None:
        self.bell_btn.set_dot(bool(self._upcoming_soon()))

    def _show_notifications(self) -> None:
        menu = QMenu(self)
        items = self._upcoming_soon()
        if not items:
            act = menu.addAction("You're all caught up.")
            act.setEnabled(False)
        else:
            menu.addAction("Starting soon:").setEnabled(False)
            for start, title, ch in items[:6]:
                act = menu.addAction(f"{start.strftime('%H:%M')}  {title}")
                act.triggered.connect(
                    lambda _=False, c=ch: self.play_channel(
                        c, self._play_context or [c]))
        menu.exec(self.bell_btn.mapToGlobal(QPoint(0, self.bell_btn.height())))

    # -- status ---------------------------------------------------------------------
    def _update_status(self) -> None:
        n_live = sum(1 for c in self.channels if c.kind == "live")
        n_mov = sum(1 for c in self.channels if c.kind == "movie")
        n_ser = sum(1 for c in self.channels if c.kind == "series")
        self.status_text.setText(
            f"Provider: {self._playlist_name()}    Channels: {len(self.channels)}"
            f"    Live: {n_live}    Movies: {n_mov}    Series: {n_ser}")
        ok = len(self.channels) > 0
        self.conn_pill.set_connected(ok)
        self.stream_dot.setText("●")
        self.stream_dot.setStyleSheet(
            f"color: {COLORS['green'] if ok else COLORS['muted']};")
        self.stream_label.setText(
            f"Stream status: {'Connected' if ok else 'Offline'}")
        self._refresh_fav_mini()

    # -- settings ---------------------------------------------------------------------
    def _open_settings(self) -> None:
        groups = sorted({c.display_group for c in self.channels
                         if c.display_group})
        dlg = SettingsDialog(self.config, self,
                             parental=self.parental, groups=groups)
        if dlg.exec():
            self.vol.setValue(self.config.volume)
            if self.config.muted != self._muted:
                self._toggle_mute()
        # PIN removal/change applies immediately, even on Cancel
        self._refresh_locks()

    def _show_details(self, channel: Channel) -> None:
        now, nxt = (self.epg.now_and_next(channel.tvg_id, channel.name)
                    if self.epg.loaded else (None, None))
        dlg = _DetailsDialog(channel, now, nxt, self)
        if dlg.exec():
            self.play_channel(channel, self._live_channels())

    # -- shutdown -----------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_stop_recording("exit"):
            event.ignore()
            return
        self._save_resume_point()
        self.config.window_geometry = bytes(self.saveGeometry())
        self.config.sync()
        self.player.stop()
        super().closeEvent(event)
