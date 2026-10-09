"""Smarters-style provider login screen (Xtream Codes login + M3U playlist).

Shown on first run (or via "Add provider") as a full-window overlay. On a
successful sign-in a ProviderProfile is created, set active, and emitted via
``authenticated``. All network work happens in QThreads; nothing runs at
import time.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QStackedWidget, QFormLayout, QButtonGroup,
)

from app.playlist import load_playlist
from app.profiles import ProfileStore, ProviderProfile
from app.xtream import (
    XtreamAuthError, XtreamClient, XtreamError, normalize_server,
)
from ui.widgets import brand_pixmap


class _XtreamLoginWorker(QThread):
    """Authenticate against an Xtream panel off the UI thread."""

    ok = Signal(object)   # {"user_info": ..., "server_info": ...}
    failed = Signal(str)

    def __init__(self, server: str, username: str, password: str) -> None:
        super().__init__()
        self.server = server
        self.username = username
        self.password = password

    def run(self) -> None:  # worker thread
        try:
            client = XtreamClient(self.server, self.username, self.password)
            info = client.login()
            self.ok.emit(info)
        except (XtreamAuthError, XtreamError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # never crash the thread silently
            self.failed.emit(f"Unexpected error: {exc}")


class _M3uCheckWorker(QThread):
    """Validate an M3U source (URL or file) off the UI thread."""

    ok = Signal(int)      # number of channels found
    failed = Signal(str)

    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source

    def run(self) -> None:  # worker thread
        try:
            channels = load_playlist(self.source)
            if not channels:
                raise ValueError("The playlist loaded but has no channels.")
            self.ok.emit(len(channels))
        except Exception as exc:
            self.failed.emit(str(exc))


class LoginScreen(QWidget):
    """Centered provider-login card with Xtream / M3U tabs."""

    authenticated = Signal(object)  # ProviderProfile

    def __init__(self, store: ProfileStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._worker: QThread | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        center = QHBoxLayout()
        center.addStretch(1)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setFixedWidth(470)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(30, 26, 30, 26)
        cl.setSpacing(10)

        # -- brand ------------------------------------------------------
        brand = QHBoxLayout()
        brand.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(brand_pixmap(44))
        brand.addWidget(mark)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        title = QLabel("NOVA IPTV")
        title.setObjectName("brandTitle")
        bt.addWidget(title)
        sub = QLabel("Sign in to your provider")
        sub.setObjectName("loginSub")
        bt.addWidget(sub)
        brand.addLayout(bt)
        brand.addStretch(1)
        cl.addLayout(brand)
        cl.addSpacing(6)

        # -- tabs -------------------------------------------------------
        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self.x_tab = QPushButton("Xtream Login")
        self.x_tab.setObjectName("loginTab")
        self.x_tab.setCheckable(True)
        self.x_tab.setChecked(True)
        self.x_tab.setCursor(Qt.PointingHandCursor)
        self.m_tab = QPushButton("M3U Playlist")
        self.m_tab.setObjectName("loginTab")
        self.m_tab.setCheckable(True)
        self.m_tab.setCursor(Qt.PointingHandCursor)
        self._tab_group.addButton(self.x_tab, 0)
        self._tab_group.addButton(self.m_tab, 1)
        tab_row.addWidget(self.x_tab)
        tab_row.addWidget(self.m_tab)
        tab_row.addStretch(1)
        cl.addLayout(tab_row)

        self._tab_stack = QStackedWidget()
        self._tab_stack.addWidget(self._build_xtream_tab())
        self._tab_stack.addWidget(self._build_m3u_tab())
        self._tab_group.idClicked.connect(self._tab_stack.setCurrentIndex)
        cl.addWidget(self._tab_stack)
        cl.addSpacing(4)

        # -- cancel (only when a provider is already active) ------------
        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("outlineBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.hide()
        cl.addWidget(self.back_btn)

        center.addWidget(card)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(1)

    # -- tab pages -----------------------------------------------------------
    def _build_xtream_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(8)
        self.x_server = QLineEdit()
        self.x_server.setPlaceholderText("https://provider.tv:8080")
        form.addRow("Server URL:", self.x_server)
        self.x_user = QLineEdit()
        self.x_user.setPlaceholderText("Username")
        form.addRow("Username:", self.x_user)
        self.x_pass = QLineEdit()
        self.x_pass.setEchoMode(QLineEdit.Password)
        self.x_pass.setPlaceholderText("Password")
        form.addRow("Password:", self.x_pass)
        self.x_name = QLineEdit("My Provider")
        self.x_name.setPlaceholderText("Profile name")
        form.addRow("Profile name:", self.x_name)
        lay.addLayout(form)
        self.x_error = QLabel("")
        self.x_error.setObjectName("loginError")
        self.x_error.setWordWrap(True)
        self.x_error.hide()
        lay.addWidget(self.x_error)
        self.x_btn = QPushButton("Sign in")
        self.x_btn.setObjectName("primaryBtn")
        self.x_btn.setCursor(Qt.PointingHandCursor)
        self.x_btn.clicked.connect(self._do_xtream_login)
        lay.addWidget(self.x_btn)
        self.x_pass.returnPressed.connect(self._do_xtream_login)
        return page

    def _build_m3u_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(8)
        self.m_url = QLineEdit()
        self.m_url.setPlaceholderText("https://example.com/playlist.m3u8")
        form.addRow("Playlist URL:", self.m_url)
        file_row = QHBoxLayout()
        self.m_file = QLineEdit()
        self.m_file.setPlaceholderText("…or pick a local file")
        browse = QPushButton("Browse…")
        browse.setObjectName("outlineBtn")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse_m3u)
        file_row.addWidget(self.m_file, 1)
        file_row.addWidget(browse)
        form.addRow("File:", file_row)
        self.m_name = QLineEdit("My Playlist")
        self.m_name.setPlaceholderText("Profile name")
        form.addRow("Profile name:", self.m_name)
        self.m_epg = QLineEdit()
        self.m_epg.setPlaceholderText("https://example.com/epg.xml (optional)")
        form.addRow("XMLTV guide:", self.m_epg)
        lay.addLayout(form)
        self.m_error = QLabel("")
        self.m_error.setObjectName("loginError")
        self.m_error.setWordWrap(True)
        self.m_error.hide()
        lay.addWidget(self.m_error)
        self.m_btn = QPushButton("Add provider")
        self.m_btn.setObjectName("primaryBtn")
        self.m_btn.setCursor(Qt.PointingHandCursor)
        self.m_btn.clicked.connect(self._do_m3u_add)
        lay.addWidget(self.m_btn)
        return page

    def _browse_m3u(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open playlist", str(Path.home()),
            "Playlists (*.m3u *.m3u8);;All files (*)",
        )
        if path:
            self.m_file.setText(path)

    # -- public --------------------------------------------------------------
    def reset(self) -> None:
        """Clear errors/secrets; call each time the screen is shown."""
        self.x_pass.clear()
        for lbl in (self.x_error, self.m_error):
            lbl.setText("")
            lbl.hide()
        self._set_busy(False)

    def set_cancellable(self, cancellable: bool) -> None:
        self.back_btn.setVisible(cancellable)

    # -- xtream flow -----------------------------------------------------------
    def _do_xtream_login(self) -> None:
        if self._busy():
            return
        server = self.x_server.text().strip()
        username = self.x_user.text().strip()
        password = self.x_pass.text()
        name = self.x_name.text().strip() or "My Provider"
        if not server or not username:
            self._fail(self.x_error, "Enter the server URL and username.")
            return
        try:
            server_n = normalize_server(server)
        except XtreamError as exc:
            self._fail(self.x_error, str(exc))
            return
        self.x_error.hide()
        self._set_busy(True, "Signing in…")
        self._worker = _XtreamLoginWorker(server_n, username, password)
        self._worker.ok.connect(
            lambda info: self._on_xtream_ok(info, server_n, username,
                                            password, name))
        self._worker.failed.connect(lambda msg: self._fail(self.x_error, msg))
        self._worker.start()

    def _on_xtream_ok(self, info: dict, server: str, username: str,
                      password: str, name: str) -> None:
        self._set_busy(False)
        profile = self._store.add(ProviderProfile(
            name=name, kind="xtream", server=server,
            username=username, password=password))
        self._store.set_active(profile.id)
        self.x_pass.clear()
        self.authenticated.emit(profile)

    # -- m3u flow --------------------------------------------------------------
    def _do_m3u_add(self) -> None:
        if self._busy():
            return
        source = self.m_url.text().strip() or self.m_file.text().strip()
        name = self.m_name.text().strip() or "My Playlist"
        epg = self.m_epg.text().strip()
        if not source:
            self._fail(self.m_error, "Enter a playlist URL or pick a file.")
            return
        self.m_error.hide()
        self._set_busy(True, "Checking playlist…")
        self._worker = _M3uCheckWorker(source)
        self._worker.ok.connect(
            lambda _n: self._on_m3u_ok(source, name, epg))
        self._worker.failed.connect(lambda msg: self._fail(self.m_error, msg))
        self._worker.start()

    def _on_m3u_ok(self, source: str, name: str, epg: str) -> None:
        self._set_busy(False)
        profile = self._store.add(ProviderProfile(
            name=name, kind="m3u", playlist_url=source, epg_url=epg))
        self._store.set_active(profile.id)
        self.authenticated.emit(profile)

    # -- helpers ---------------------------------------------------------------
    def _busy(self) -> bool:
        return not self.x_btn.isEnabled()

    def _set_busy(self, busy: bool, text: str = "") -> None:
        for btn, label in ((self.x_btn, "Sign in"), (self.m_btn, "Add provider")):
            btn.setEnabled(not busy)
            if busy:
                btn.setText(text)
            else:
                btn.setText(label)

    def _fail(self, label: QLabel, msg: str) -> None:
        self._set_busy(False)
        label.setText(msg)
        label.show()
