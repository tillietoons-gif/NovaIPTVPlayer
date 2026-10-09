"""Dialogs: add-playlist wizard and settings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTabWidget, QWidget, QSpinBox,
    QFormLayout, QDialogButtonBox, QCheckBox,
)


class AddPlaylistDialog(QDialog):
    """Collect an M3U source (URL or file) plus an optional XMLTV source."""

    def __init__(self, playlist: str = "", epg: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add playlist")
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)

        tabs = QTabWidget()
        # --- URL tab ---
        url_tab = QWidget()
        url_form = QFormLayout(url_tab)
        self.url_edit = QLineEdit(playlist if playlist.startswith("http") else "")
        self.url_edit.setPlaceholderText("https://example.com/playlist.m3u8")
        url_form.addRow("Playlist URL:", self.url_edit)
        tabs.addTab(url_tab, "From URL")
        # --- File tab ---
        file_tab = QWidget()
        file_lay = QHBoxLayout(file_tab)
        self.file_edit = QLineEdit(
            playlist if playlist and not playlist.startswith("http") else ""
        )
        self.file_edit.setPlaceholderText("C:\\playlists\\mylist.m3u")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        file_lay.addWidget(self.file_edit, 1)
        file_lay.addWidget(browse)
        tabs.addTab(file_tab, "From file")
        lay.addWidget(tabs)

        epg_form = QFormLayout()
        self.epg_edit = QLineEdit(epg)
        self.epg_edit.setPlaceholderText("https://example.com/epg.xml (optional)")
        epg_form.addRow("XMLTV guide:", self.epg_edit)
        lay.addLayout(epg_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open playlist", str(Path.home()),
            "Playlists (*.m3u *.m3u8);;All files (*)",
        )
        if path:
            self.file_edit.setText(path)

    def playlist_source(self) -> str:
        if self.url_edit.text().strip():
            return self.url_edit.text().strip()
        return self.file_edit.text().strip()

    def epg_source(self) -> str:
        return self.epg_edit.text().strip()


class SettingsDialog(QDialog):
    """Playback / UI preferences."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(380)

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(0, 125)
        self.volume_spin.setValue(config.volume)
        form.addRow("Default volume:", self.volume_spin)

        self.mute_check = QCheckBox("Start muted")
        self.mute_check.setChecked(config.muted)
        form.addRow(self.mute_check)

        lay.addLayout(form)

        note = QLabel(
            "Tip: VLC 64-bit must be installed on Windows for playback.\n"
            "python-vlc uses the VLC libraries from the install folder."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8b95a9; font-size:11px;")
        lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self) -> None:
        self._config.volume = self.volume_spin.value()
        self._config.muted = self.mute_check.isChecked()
        self._config.sync()
        self.accept()
