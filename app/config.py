"""Application settings backed by QSettings (native registry/plist/ini storage)."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from app import __app_name__


class AppConfig:
    """Thin typed wrapper around QSettings so the rest of the app never
    touches raw string keys."""

    def __init__(self) -> None:
        self._s = QSettings(__app_name__, __app_name__)

    # -- playlist ---------------------------------------------------------
    @property
    def playlist_source(self) -> str:
        return str(self._s.value("playlist/source", ""))

    @playlist_source.setter
    def playlist_source(self, value: str) -> None:
        self._s.setValue("playlist/source", value)

    @property
    def epg_source(self) -> str:
        return str(self._s.value("epg/source", ""))

    @epg_source.setter
    def epg_source(self, value: str) -> None:
        self._s.setValue("epg/source", value)

    def clear_playlist(self) -> None:
        """Forget the configured playlist and its guide."""
        self._s.remove("playlist/source")
        self._s.remove("epg/source")
        self.sync()

    # -- playback ---------------------------------------------------------
    @property
    def volume(self) -> int:
        return int(self._s.value("player/volume", 80))

    @volume.setter
    def volume(self, value: int) -> None:
        self._s.setValue("player/volume", max(0, min(125, value)))

    @property
    def muted(self) -> bool:
        return bool(self._s.value("player/muted", False))

    @muted.setter
    def muted(self, value: bool) -> None:
        self._s.setValue("player/muted", value)

    @property
    def last_channel_url(self) -> str:
        return str(self._s.value("player/last_channel", ""))

    @last_channel_url.setter
    def last_channel_url(self, value: str) -> None:
        self._s.setValue("player/last_channel", value)

    # -- ui ---------------------------------------------------------------
    @property
    def window_geometry(self) -> bytes | None:
        g = self._s.value("ui/geometry")
        return bytes(g) if g else None

    @window_geometry.setter
    def window_geometry(self, value: bytes) -> None:
        self._s.setValue("ui/geometry", value)

    def sync(self) -> None:
        self._s.sync()
