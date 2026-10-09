"""Main window: frameless Nova IPTV dashboard (sidebar, top bar, pages,
right Now-Playing panel, status bar)."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QThread, Signal, QPoint
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QLabel, QSlider, QComboBox, QMessageBox,
    QScrollArea, QDialog, QDialogButtonBox, QMenu, QFormLayout,
)

from app import __app_name__, __version__
from app.config import AppConfig
from app.epg import EPGManager
from app.favorites import FavoritesStore
from app.models import Channel, EPGProgram
from app.player import Player
from app.playlist import (
    load_playlist, categories, filter_channels,
)
from ui.dialogs import AddPlaylistDialog, SettingsDialog
from ui.theme import COLORS
from ui.widgets import (
    ChannelGrid, SearchBar, VideoWidget, NavButton, IconButton, WinButton,
    SectionHeader, StatPill, ChannelCard, PosterCard, HeroCard,
    LogoLabel, brand_pixmap, avatar_pixmap, make_icon, poster_pixmap,
)


# -- background loaders (Qt threads, not asyncio: simpler on Windows) --------

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


# -- small helpers ---------------------------------------------------------------

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


class _FullscreenVideo(QDialog):
    """Fullscreen playback window (Esc to exit)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Now Playing")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.video = VideoWidget(placeholder="")
        lay.addWidget(self.video)
        self.showFullScreen()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


class _ConnectionDialog(QDialog):
    def __init__(self, config: AppConfig, stats: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Playlist:", QLabel(config.playlist_source or "Not configured"))
        form.addRow("Guide (XMLTV):", QLabel(config.epg_source or "Not configured"))
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


# -- main window ---------------------------------------------------------------

NAV_ITEMS = [
    ("home", "Home", "home"),
    ("live", "Live TV", "tv"),
    ("movie", "Movies", "film"),
    ("series", "TV Series", "layers"),
    ("catchup", "Catch-up", "replay"),
    ("favorites", "Favorites", "star"),
    ("history", "Recently Watched", "history"),
    ("playlists", "Playlists", "list"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowTitle(f"{__app_name__} — IPTV Player")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        self.config = AppConfig()
        self.favorites = FavoritesStore()
        self.epg = EPGManager()
        self.player = Player(self)

        self.channels: list[Channel] = []
        self.history: list[tuple[str, str, str]] = []  # (name, url, played_at)
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
        self._count_labels: dict[str, QLabel] = {}
        self.category_boxes: dict[str, QComboBox] = {}
        self.grids: dict[str, ChannelGrid] = {}

        self._build_ui()
        self._connect_player()
        self._refresh_home()

        geom = self.config.window_geometry
        if geom:
            self.restoreGeometry(geom)

        if self.config.playlist_source:
            self._load_playlist(self.config.playlist_source, silent=True)
        if self.config.epg_source:
            self._load_epg(self.config.epg_source, silent=True)
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

        root.addWidget(self._build_titlebar())

        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)
        mid.addWidget(self._build_sidebar())

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        for key, _label, _icon in NAV_ITEMS:
            page = self._build_page(key)
            self._pages[key] = page
            self.stack.addWidget(page)
        content.addWidget(self.stack, 1)
        content.addWidget(self._build_statusbar())
        mid.addLayout(content, 1)

        self.right_panel = self._build_right_panel()
        mid.addWidget(self.right_panel)
        root.addLayout(mid, 1)

        self._nav_btns["home"].setChecked(True)

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
        self.search.textChanged.connect(self._on_search)
        lay.addWidget(self.search)
        lay.addStretch(1)

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
        side.setFixedWidth(212)
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
        brand.addWidget(title)
        brand.addStretch(1)
        lay.addLayout(brand)
        lay.addSpacing(14)

        self._nav_btns: dict[str, NavButton] = {}
        for key, label, icon in NAV_ITEMS:
            btn = NavButton(icon, label)
            btn.clicked.connect(partial(self._navigate, key))
            lay.addWidget(btn)
            self._nav_btns[key] = btn
        lay.addStretch(1)

        mgr = NavButton("folder", "Playlist manager")
        mgr.setCheckable(False)
        mgr.clicked.connect(self._open_add_dialog)
        lay.addWidget(mgr)
        conn = NavButton("signal", "Connection")
        conn.setCheckable(False)
        conn.clicked.connect(self._open_connection)
        lay.addWidget(conn)
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
        user.addWidget(name)
        user.addStretch(1)
        lay.addLayout(user)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("versionLabel")
        ver.setAlignment(Qt.AlignCenter)
        lay.addWidget(ver)
        return side

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        self.status_text = QLabel("Playlist: —")
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

    # -- pages ------------------------------------------------------------------
    def _build_page(self, key: str) -> QWidget:
        if key == "home":
            return self._build_home_page()
        if key in ("live", "movie", "series"):
            return self._build_grid_page(key)
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
        lay.addWidget(grid, 1)
        self.grids[key] = grid
        return page

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
            lambda: self._load_epg(self.config.epg_source))
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
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(12)
        lay.addLayout(self._page_header("Playlists"))
        self.playlist_card = QFrame()
        self.playlist_card.setObjectName("sideCard")
        lay.addWidget(self.playlist_card)
        add_btn = QPushButton("  Add playlist")
        add_btn.setObjectName("primaryBtn")
        add_btn.setIcon(make_icon("plus", 16, "white"))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._open_add_dialog)
        lay.addWidget(add_btn, 0, Qt.AlignLeft)
        lay.addStretch(1)
        return page

    def _refresh_playlist_card(self) -> None:
        lay = self.playlist_card.layout()
        if lay is None:
            lay = QVBoxLayout(self.playlist_card)
            lay.setContentsMargins(20, 18, 20, 18)
            lay.setSpacing(6)
        self._clear_layout(lay)
        name = QLabel(self._playlist_name())
        name.setObjectName("sideTitle")
        lay.addWidget(name)
        src = QLabel(self.config.playlist_source or "No playlist configured")
        src.setObjectName("cardMeta")
        src.setWordWrap(True)
        lay.addWidget(src)
        n_live = sum(1 for c in self.channels if c.kind == "live")
        n_mov = sum(1 for c in self.channels if c.kind == "movie")
        n_ser = sum(1 for c in self.channels if c.kind == "series")
        lay.addWidget(QLabel(
            f"{len(self.channels)} channels  •  {n_live} live  •  "
            f"{n_mov} movies  •  {n_ser} series"))
        epg = QLabel(f"Guide: {self.config.epg_source or 'not configured'}")
        epg.setObjectName("cardMeta")
        epg.setWordWrap(True)
        lay.addWidget(epg)

    # -- right panel ---------------------------------------------------------------
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPanel")
        panel.setFixedWidth(292)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 18, 16, 16)
        lay.setSpacing(10)

        t = QLabel("Now Playing")
        t.setObjectName("sideTitle")
        lay.addWidget(t)

        card = QFrame()
        card.setObjectName("sideCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(8)
        self.thumb_video = VideoWidget(placeholder="Select a channel to play")
        self.thumb_video.setFixedHeight(150)
        cl.addWidget(self.thumb_video)
        self.np_title = QLabel("Nothing playing")
        self.np_title.setObjectName("cardName")
        self.np_title.setWordWrap(True)
        cl.addWidget(self.np_title)
        self.np_meta = QLabel("")
        self.np_meta.setObjectName("cardMeta")
        cl.addWidget(self.np_meta)
        lay.addWidget(card)

        transport = QHBoxLayout()
        transport.setSpacing(8)
        self.prev_btn = self._tbtn("prev", self._play_prev)
        self.pp_btn = self._tbtn("play", self._toggle_pause)
        self.next_btn = self._tbtn("next", self._play_next)
        self.fs_btn = self._tbtn("expand", self._toggle_fullscreen)
        for b in (self.prev_btn, self.pp_btn, self.next_btn):
            transport.addWidget(b)
        transport.addStretch(1)
        transport.addWidget(self.fs_btn)
        lay.addLayout(transport)

        vol_row = QHBoxLayout()
        self.mute_btn = IconButton("signal", 18)
        # reuse: show volume state via text-less icon button
        self.mute_btn.setIcon(make_icon("signal", 18, COLORS["muted"]))
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
        self.player.set_mute(self.config.muted)
        self.player.set_volume(self.config.volume)
        self.player.attach(self.thumb_video)
        self._update_mute_icon()

    # -- navigation -----------------------------------------------------------
    def _navigate(self, key: str) -> None:
        for k, btn in self._nav_btns.items():
            btn.setChecked(k == key)
        idx = [k for k, _l, _i in NAV_ITEMS].index(key)
        self.stack.setCurrentIndex(idx)
        self._current_page = key
        self.right_panel.setVisible(key in ("home", "live"))
        if key in ("live", "movie", "series"):
            self._current_kind = key
            self._refresh_grid()
        elif key == "favorites":
            self._current_kind = None
            self._refresh_grid()
        elif key == "home":
            self._refresh_home()
        elif key == "catchup":
            self._refresh_catchup()
        elif key == "history":
            self._refresh_history_page()
        elif key == "playlists":
            self._refresh_playlist_card()

    def _on_search(self, text: str) -> None:
        if self._current_page == "home" and text.strip():
            self._navigate("live")
            return
        if self._current_page in ("live", "movie", "series", "favorites"):
            self._refresh_grid()

    def _on_category_changed(self, text: str) -> None:
        self._current_category = "" if text == "All categories" else text
        self._refresh_grid()

    # -- playlist -------------------------------------------------------------
    def _playlist_name(self) -> str:
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
            self.config, {"channels": len(self.channels)}, self)
        dlg.exec()

    def _load_playlist(self, source: str, silent: bool = False) -> None:
        if self._loader and self._loader.isRunning():
            return
        self._loader = _PlaylistLoader(source)
        self._loader.finished_ok.connect(self._on_playlist_loaded)
        self._loader.failed.connect(
            lambda msg: QMessageBox.warning(
                self, "Playlist failed",
                f"Could not load the playlist:\n{msg}"))
        self._loader.start()

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
        self._current_category = ""
        self._update_status()
        self._refresh_grid()
        self._refresh_home()
        self._refresh_playlist_card()
        self._update_bell()

    # -- EPG ------------------------------------------------------------------
    def _load_epg(self, source: str, silent: bool = False) -> None:
        if not source:
            if not silent:
                QMessageBox.information(
                    self, "EPG", "Add an XMLTV guide URL first (Playlist manager).")
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
        if self._current_page == "catchup":
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
            featured = live[0] if live else (
                self.channels[0] if self.channels else None)
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
            self.home_live_row.addWidget(card)
        self.home_live_row.addStretch(1)

        # continue watching
        self._clear_layout(self.home_hist_row)
        for name, url, played_at in self.history[:8]:
            ch = next((c for c in self.channels if c.url == url), None)
            if ch is None:
                ch = Channel(name=name, url=url)
            pos, dur = self._progress.get(url, (0, 0))
            pct = (pos / dur) if dur > 0 else 0.0
            card = PosterCard(ch, pct, f"Watched {played_at}")
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
        if key == "favorites":
            visible = self._visible_channels()
            self._context_lists[key] = visible
            self.grids[key].set_channels(
                visible, self.favorites.all(), self._epg_label)
        else:
            visible = self._visible_channels()
            self._context_lists[key] = visible
            self.grids[key].set_channels(
                visible, self.favorites.all(), self._epg_label)
        self._count_labels[key].setText(f"{len(self._context_lists[key])} items")
        self.grids[key].mark_selected(
            self._current_channel.url if self._current_channel else None)

    def _play_from(self, key: str, channel: Channel) -> None:
        self.play_channel(channel, self._context_lists.get(key, [channel]))

    def _on_fav_toggled(self, channel: Channel, state: bool) -> None:
        self.favorites.toggle(channel.url)
        for grid in self.grids.values():
            grid.update_favorite(channel.url, state)
        if self._current_page == "favorites":
            self._refresh_grid()
        self._refresh_fav_mini()

    # -- catch-up -----------------------------------------------------------------
    def _refresh_catchup(self) -> None:
        self._clear_layout(self.catchup_lay)
        if not self.epg.loaded:
            lbl = QLabel(
                "Load an XMLTV guide to see today's programmes.\n"
                "Add the guide URL via Playlist manager.")
            lbl.setObjectName("cardMeta")
            lbl.setAlignment(Qt.AlignCenter)
            self.catchup_lay.addWidget(lbl)
            self.catchup_lay.addStretch(1)
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
            lbl = QLabel("No programmes found for today.")
            lbl.setObjectName("cardMeta")
            lbl.setAlignment(Qt.AlignCenter)
            self.catchup_lay.addWidget(lbl)
            self.catchup_lay.addStretch(1)
            return
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
            watch = QPushButton("Watch channel")
            watch.setObjectName("outlineBtn")
            watch.setCursor(Qt.PointingHandCursor)
            watch.clicked.connect(
                lambda _=False, c=ch: self.play_channel(c, self._live_channels()))
            hl.addWidget(watch)
            self.catchup_lay.addWidget(row)
        self.catchup_lay.addStretch(1)

    # -- history page ---------------------------------------------------------------
    def _refresh_history_page(self) -> None:
        self._clear_layout(self.history_lay)
        if not self.history:
            lbl = QLabel("Nothing watched yet. Play a channel to see it here.")
            lbl.setObjectName("cardMeta")
            lbl.setAlignment(Qt.AlignCenter)
            self.history_lay.addWidget(lbl)
            self.history_lay.addStretch(1)
            return
        for name, url, played_at in self.history:
            ch = next((c for c in self.channels if c.url == url), None)
            if ch is None:
                ch = Channel(name=name, url=url)
            row = QFrame()
            row.setObjectName("sideCard")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(12, 8, 12, 8)
            art = QLabel()
            art.setPixmap(poster_pixmap(96, 64, name, url))
            hl.addWidget(art)
            txt = QVBoxLayout()
            title = QLabel(name)
            title.setObjectName("cardName")
            txt.addWidget(title)
            txt.addWidget(QLabel(f"Watched {played_at}"))
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

        self.thumb_video.clear()
        self.player.play(channel.url)
        self.player.set_volume(self.vol.value())
        self.player.set_mute(self._muted)

        self.np_title.setText(channel.name)
        self.np_meta.setText(
            f"{channel.display_group}  •  {channel.kind.title()}")
        for grid in self.grids.values():
            grid.mark_selected(channel.url)

        self.config.last_channel_url = channel.url
        self.config.sync()
        stamp = datetime.now().strftime("%H:%M")
        self.history = [(n, u, t) for n, u, t in self.history
                        if u != channel.url]
        self.history.insert(0, (channel.name, channel.url, stamp))
        self.history = self.history[:30]

        self._update_now_next()
        if self._current_page == "home":
            self._refresh_home()

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
        dlg = _FullscreenVideo(self)
        try:
            self.player.frame_ready.disconnect(self.thumb_video.set_frame)
        except (RuntimeError, TypeError):
            pass
        self.player.frame_ready.connect(dlg.video.set_frame)
        dlg.exec()
        try:
            self.player.frame_ready.disconnect(dlg.video.set_frame)
        except (RuntimeError, TypeError):
            pass
        self.player.frame_ready.connect(self.thumb_video.set_frame)

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
            "close" if self._muted else "signal", 18,
            COLORS["red"] if self._muted else COLORS["muted"]))
        self.mute_btn.setToolTip("Unmute" if self._muted else "Mute")

    def _on_position(self, pos_ms: int, dur_ms: int) -> None:
        if self._current_channel:
            self._progress[self._current_channel.url] = (pos_ms, dur_ms)

    def _on_player_state(self, state: str) -> None:
        if state == "playing":
            self.pp_btn.setIcon(make_icon("pause", 18))
        elif state == "paused":
            self.pp_btn.setIcon(make_icon("play", 18))
        elif state in ("stopped", "error"):
            self.pp_btn.setIcon(make_icon("play", 18))
        if state == "error":
            QMessageBox.warning(
                self, "Playback error",
                "The built-in player could not play this stream.\n"
                "It may be offline, geo-blocked, use an unsupported codec, "
                "or the playlist URL expired.")

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
            f"Playlist: {self._playlist_name()}    Channels: {len(self.channels)}"
            f"    Movies: {n_mov}    Series: {n_ser}")
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
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.vol.setValue(self.config.volume)
            if self.config.muted != self._muted:
                self._toggle_mute()

    def _show_details(self, channel: Channel) -> None:
        now, nxt = (self.epg.now_and_next(channel.tvg_id, channel.name)
                    if self.epg.loaded else (None, None))
        dlg = _DetailsDialog(channel, now, nxt, self)
        if dlg.exec():
            self.play_channel(channel, self._live_channels())

    # -- shutdown -----------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.config.window_geometry = bytes(self.saveGeometry())
        self.config.sync()
        self.player.stop()
        super().closeEvent(event)
