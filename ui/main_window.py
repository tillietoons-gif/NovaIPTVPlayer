"""Main window: sidebar navigation, channel grids, EPG guide, video player."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QLabel, QFrame, QSlider, QComboBox, QSplitter,
    QMessageBox, QStatusBar, QListWidget, QListWidgetItem, QProgressBar,
)

from app import __app_name__
from app.config import AppConfig
from app.epg import EPGManager
from app.favorites import FavoritesStore
from app.models import Channel
from app.player import VlcPlayer
from app.playlist import (
    load_playlist, categories, filter_channels,
)
from ui.dialogs import AddPlaylistDialog, SettingsDialog
from ui.widgets import ChannelGrid, SearchBar, EpgTimelineWidget


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


# -- main window ---------------------------------------------------------------

NAV_ITEMS = [
    ("📡", "Live TV", "live"),
    ("🎬", "Movies", "movie"),
    ("🍿", "Series", "series"),
    ("⭐", "Favorites", "favorites"),
    ("🗓", "EPG Guide", "guide"),
    ("⚙", "Settings", "settings"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{__app_name__} — IPTV Player")
        self.resize(1280, 800)

        self.config = AppConfig()
        self.favorites = FavoritesStore()
        self.epg = EPGManager()
        self.player = VlcPlayer(self)

        self.channels: list[Channel] = []
        self.history: list[tuple[str, str]] = []  # (name, url)
        self._current_kind: str | None = "live"
        self._current_category = ""
        self._loader: _PlaylistLoader | None = None
        self._epg_loader: _EpgLoader | None = None

        self._build_ui()
        self._connect_player()

        geom = self.config.window_geometry
        if geom:
            self.restoreGeometry(geom)

        # Auto-load the last playlist if we have one.
        if self.config.playlist_source:
            self._load_playlist(self.config.playlist_source, silent=True)
        if self.config.epg_source:
            self._load_epg(self.config.epg_source, silent=True)
        if not VlcPlayer.is_available():
            err = VlcPlayer.import_error()
            QMessageBox.warning(
                self, "VLC not found",
                "python-vlc could not load libvlc.\n\n"
                "On Windows, install VLC 64-bit from videolan.org "
                "(matching your Python bitness) and restart.\n\n"
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

        # Top bar: brand + search + playlist buttons.
        top = QHBoxLayout()
        top.setContentsMargins(16, 10, 16, 10)
        brand = QLabel(f"⚡ {__app_name__}")
        brand.setObjectName("brandLabel")
        top.addWidget(brand)
        self.search = SearchBar()
        self.search.setMaximumWidth(420)
        self.search.textChanged.connect(self._refresh_grid)
        top.addWidget(self.search, 1)
        self.add_btn = QPushButton("＋ Playlist")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.clicked.connect(self._open_add_dialog)
        top.addWidget(self.add_btn)
        root.addLayout(top)

        # Middle: sidebar + content.
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(10, 10, 10, 10)
        side_lay.setSpacing(6)
        self._nav_btns: dict[str, QPushButton] = {}
        for icon, label, key in NAV_ITEMS:
            btn = QPushButton(f"{icon}  {label}")
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=key: self._navigate(k))
            side_lay.addWidget(btn)
            self._nav_btns[key] = btn
        side_lay.addStretch(1)
        self.status_line = QLabel("No playlist loaded")
        self.status_line.setWordWrap(True)
        self.status_line.setStyleSheet("color:#8b95a9; font-size:11px; padding:6px;")
        side_lay.addWidget(self.status_line)
        mid.addWidget(sidebar)

        # Content stack.
        self.stack = QStackedWidget()
        mid.addWidget(self.stack, 1)

        # Pages per content kind.
        self.grids: dict[str, ChannelGrid] = {}
        self.category_boxes: dict[str, QComboBox] = {}
        for key in ("live", "movie", "series", "favorites"):
            page = QWidget()
            lay = QVBoxLayout(page)
            cat = QComboBox()
            cat.addItem("All categories")
            cat.currentTextChanged.connect(self._on_category_changed)
            lay.addWidget(cat)
            self.category_boxes[key] = cat
            grid = ChannelGrid(columns=3)
            grid.channel_chosen.connect(self.play_channel)
            grid.fav_toggled.connect(self._on_fav_toggled)
            lay.addWidget(grid, 1)
            self.grids[key] = grid
            self.stack.addWidget(page)

        # EPG guide page.
        guide_page = QWidget()
        glay = QVBoxLayout(guide_page)
        guide_head = QHBoxLayout()
        guide_head.addWidget(QLabel("<b>Programme guide</b> (next 6h)"))
        self.epg_reload_btn = QPushButton("↻ Reload guide")
        self.epg_reload_btn.setObjectName("ctlBtn")
        self.epg_reload_btn.clicked.connect(
            lambda: self._load_epg(self.config.epg_source))
        guide_head.addStretch(1)
        guide_head.addWidget(self.epg_reload_btn)
        glay.addLayout(guide_head)
        self.guide = EpgTimelineWidget()
        self.guide.channel_chosen.connect(self.play_channel)
        glay.addWidget(self.guide, 1)
        self.stack.addWidget(guide_page)

        # Settings page (embedded quick settings + dialog shortcut).
        settings_page = QWidget()
        slay = QVBoxLayout(settings_page)
        slay.addWidget(QLabel("<b>Settings</b>"))
        open_settings = QPushButton("Open settings…")
        open_settings.setObjectName("ctlBtn")
        open_settings.clicked.connect(self._open_settings)
        slay.addWidget(open_settings, 0, Qt.AlignLeft)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(220)
        self.history_list.itemDoubleClicked.connect(self._play_history_item)
        slay.addWidget(QLabel("Recent history (double-click to replay):"))
        slay.addWidget(self.history_list)
        slay.addStretch(1)
        self.stack.addWidget(settings_page)

        root.addLayout(mid, 1)

        # Bottom player bar.
        bar = QWidget()
        bar.setObjectName("playerBar")
        blay = QVBoxLayout(bar)
        blay.setContentsMargins(16, 8, 16, 10)
        blay.setSpacing(6)

        info = QHBoxLayout()
        self.video_frame = QFrame()
        self.video_frame.setObjectName("videoFrame")
        self.video_frame.setMinimumHeight(300)
        blay.addWidget(self.video_frame, 1)

        self.now_playing = QLabel("Nothing playing")
        self.now_playing.setObjectName("nowPlaying")
        self.now_next = QLabel("")
        self.now_next.setObjectName("nowNext")
        info.addWidget(self.now_playing, 1)
        info.addWidget(self.now_next, 1)
        self.buffer = QProgressBar()
        self.buffer.setRange(0, 0)  # indeterminate
        self.buffer.setVisible(False)
        self.buffer.setMaximumWidth(160)
        info.addWidget(self.buffer)
        blay.addLayout(info)

        ctrls = QHBoxLayout()
        self.play_pause_btn = QPushButton("⏸ Pause")
        self.play_pause_btn.setObjectName("ctlBtn")
        self.play_pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setObjectName("ctlBtn")
        self.stop_btn.clicked.connect(self._stop)
        self.fs_btn = QPushButton("⛶ Fullscreen")
        self.fs_btn.setObjectName("ctlBtn")
        self.fs_btn.clicked.connect(self._toggle_fullscreen)
        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setObjectName("ctlBtn")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setChecked(self.config.muted)
        self.mute_btn.clicked.connect(self._toggle_mute)
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 125)
        self.vol.setValue(self.config.volume)
        self.vol.setMaximumWidth(160)
        self.vol.valueChanged.connect(self._on_volume)
        ctrls.addWidget(self.play_pause_btn)
        ctrls.addWidget(self.stop_btn)
        ctrls.addWidget(self.fs_btn)
        ctrls.addStretch(1)
        ctrls.addWidget(QLabel("Volume"))
        ctrls.addWidget(self.vol)
        ctrls.addWidget(self.mute_btn)
        blay.addLayout(ctrls)

        root.addWidget(bar)

        self.setStatusBar(QStatusBar())

        self._nav_btns["live"].setChecked(True)
        # Split content/player vertically is handled by layout stretch.

    def _connect_player(self) -> None:
        self.player.state_changed.connect(self._on_player_state)
        self.player.set_mute(self.config.muted)
        self.player.set_volume(self.config.volume)
        # Attach once the video widget has a real window handle.
        QTimer.singleShot(300, lambda: self.player.attach(self.video_frame))

    # -- navigation -----------------------------------------------------------
    def _navigate(self, key: str) -> None:
        for k, btn in self._nav_btns.items():
            btn.setChecked(k == key)
        idx = {"live": 0, "movie": 1, "series": 2, "favorites": 3,
               "guide": 4, "settings": 5}[key]
        self.stack.setCurrentIndex(idx)
        if key in ("live", "movie", "series"):
            self._current_kind = key
            self._refresh_grid()
        elif key == "favorites":
            self._current_kind = None
            self._refresh_grid()
        elif key == "guide":
            self._refresh_guide()

    def _on_category_changed(self, text: str) -> None:
        self._current_category = "" if text == "All categories" else text
        self._refresh_grid()

    # -- playlist -------------------------------------------------------------
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

    def _load_playlist(self, source: str, silent: bool = False) -> None:
        if self._loader and self._loader.isRunning():
            return
        if not silent:
            self.statusBar().showMessage("Loading playlist…")
        self._loader = _PlaylistLoader(source)
        self._loader.finished_ok.connect(self._on_playlist_loaded)
        self._loader.failed.connect(
            lambda msg: self.statusBar().showMessage(f"Playlist failed: {msg}"))
        self._loader.start()

    def _on_playlist_loaded(self, channels: list[Channel]) -> None:
        self.channels = channels
        n_live = sum(1 for c in channels if c.kind == "live")
        n_mov = sum(1 for c in channels if c.kind == "movie")
        n_ser = sum(1 for c in channels if c.kind == "series")
        self.status_line.setText(
            f"{len(channels)} channels\n{n_live} live · {n_mov} movies · {n_ser} series")
        self.statusBar().showMessage(
            f"Loaded {len(channels)} channels", 5000)
        for key, kind in (("live", "live"), ("movie", "movie"),
                          ("series", "series")):
            box = self.category_boxes[key]
            box.blockSignals(True)
            box.clear()
            box.addItem("All categories")
            box.addItems(categories(channels, kind))
            box.blockSignals(False)
        self._current_category = ""
        self._refresh_grid()

    # -- EPG ------------------------------------------------------------------
    def _load_epg(self, source: str, silent: bool = False) -> None:
        if not source:
            if not silent:
                QMessageBox.information(
                    self, "EPG", "Add an XMLTV guide URL first (＋ Playlist).")
            return
        if self._epg_loader and self._epg_loader.isRunning():
            return
        if not silent:
            self.statusBar().showMessage("Loading EPG…")
        self._epg_loader = _EpgLoader(self.epg, source)
        self._epg_loader.finished_ok.connect(
            lambda n: self.statusBar().showMessage(f"EPG loaded: {n} programmes", 5000))
        self._epg_loader.finished_ok.connect(lambda _n: self._refresh_guide())
        self._epg_loader.failed.connect(
            lambda msg: self.statusBar().showMessage(f"EPG failed: {msg}"))
        self._epg_loader.start()

    def _epg_label(self, ch: Channel) -> str:
        if not self.epg.loaded:
            return ch.display_group
        now, nxt = self.epg.now_and_next(ch.tvg_id, ch.name)
        parts = []
        if now:
            parts.append(f"▶ {now.title} ({now.start.strftime('%H:%M')})")
        if nxt:
            parts.append(f"Next: {nxt.title} ({nxt.start.strftime('%H:%M')})")
        return " · ".join(parts) if parts else ch.display_group

    def _refresh_guide(self) -> None:
        items: list[tuple[Channel, list[EPGProgram]]] = []
        for ch in [c for c in self.channels if c.kind == "live"][:60]:
            items.append((ch, self.epg.guide_window(ch.tvg_id, ch.name)))
        self.guide.set_guide(items)

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
        if self._current_kind is None:
            self.grids["favorites"].set_channels(
                self._visible_channels(), self.favorites.all(), self._epg_label)
            return
        key = self._current_kind
        self.grids[key].set_channels(
            self._visible_channels(), self.favorites.all(), self._epg_label)

    def _on_fav_toggled(self, channel: Channel, state: bool) -> None:
        self.favorites.toggle(channel.url)
        for grid in self.grids.values():
            grid.update_favorite(channel.url, state)
        if self._current_kind is None:
            self._refresh_grid()  # keep favorites page in sync
        self.statusBar().showMessage(
            f"{'Added to' if state else 'Removed from'} favorites: {channel.name}",
            3000)

    # -- playback ---------------------------------------------------------------
    def play_channel(self, channel: Channel) -> None:
        self.player.play(channel.url)
        self.player.set_volume(self.vol.value())
        self.player.set_mute(self.mute_btn.isChecked())
        self.now_playing.setText(f"▶ {channel.name}")
        now, nxt = (self.epg.now_and_next(channel.tvg_id, channel.name)
                    if self.epg.loaded else (None, None))
        detail = []
        if now:
            detail.append(f"Now: {now.title}")
        if nxt:
            detail.append(f"Next: {nxt.title} @ {nxt.start.strftime('%H:%M')}")
        self.now_next.setText(" · ".join(detail))
        self.config.last_channel_url = channel.url
        self.config.sync()
        # History (most recent first, deduped, capped at 30).
        self.history = [(n, u) for n, u in self.history if u != channel.url]
        self.history.insert(0, (channel.name,
                                channel.url))
        self.history = self.history[:30]
        self._refresh_history()
        self.statusBar().showMessage(f"Playing: {channel.name}", 4000)

    def _refresh_history(self) -> None:
        self.history_list.clear()
        for name, url in self.history:
            item = QListWidgetItem(
                f"{name}  —  {datetime.now().strftime('%H:%M')}")
            item.setData(Qt.UserRole, (name, url))
            self.history_list.addItem(item)

    def _play_history_item(self, item: QListWidgetItem) -> None:
        name, url = item.data(Qt.UserRole)
        match = next((c for c in self.channels if c.url == url), None)
        self.play_channel(match if match else Channel(name=name, url=url))

    def _toggle_pause(self) -> None:
        self.player.toggle_pause()

    def _stop(self) -> None:
        self.player.stop()
        self.now_playing.setText("Nothing playing")
        self.now_next.setText("")

    def _toggle_fullscreen(self) -> None:
        if self.video_frame.isFullScreen():
            self.video_frame.setWindowFlags(Qt.Widget)
            self.video_frame.showNormal()
        else:
            # Re-attach after going fullscreen: the native handle changes.
            self.video_frame.setWindowFlags(Qt.Window)
            self.video_frame.showFullScreen()
            QTimer.singleShot(200, lambda: self.player.attach(self.video_frame))

    def _on_volume(self, value: int) -> None:
        self.player.set_volume(value)
        self.config.volume = value

    def _toggle_mute(self, checked: bool) -> None:
        self.player.set_mute(checked)
        self.mute_btn.setText("🔇" if checked else "🔊")
        self.config.muted = checked

    def _on_player_state(self, state: str) -> None:
        self.buffer.setVisible(state == "buffering")
        if state == "playing":
            self.play_pause_btn.setText("⏸ Pause")
        elif state == "paused":
            self.play_pause_btn.setText("▶ Resume")
        elif state == "error":
            self.statusBar().showMessage(
                "Playback error — the stream may be offline or the URL expired.",
                6000)
            QMessageBox.warning(
                self, "Playback error",
                "VLC could not play this stream.\n"
                "It may be offline, geo-blocked, or the playlist URL expired.")
        self.statusBar().showMessage(f"Player: {state}", 3000)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.vol.setValue(self.config.volume)
            self.mute_btn.setChecked(self.config.muted)
            self._toggle_mute(self.config.muted)

    # -- shutdown -----------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.config.window_geometry = bytes(self.saveGeometry())
        self.config.sync()
        self.player.stop()
        super().closeEvent(event)
