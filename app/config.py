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

    # -- playback ---------------------------------------------------------
    @property
    def volume(self) -> int:
        return int(self._s.value("player/volume", 80, type=int))

    @volume.setter
    def volume(self, value: int) -> None:
        self._s.setValue("player/volume", max(0, min(125, value)))

    @property
    def muted(self) -> bool:
        return self._s.value("player/muted", False, type=bool)

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

    @property
    def sidebar_width(self) -> int:
        return int(self._s.value("ui/sidebar_width", 212, type=int))

    @sidebar_width.setter
    def sidebar_width(self, value: int) -> None:
        self._s.setValue("ui/sidebar_width", max(64, min(420, value)))

    # -- advanced playback & engine ---------------------------------------
    @property
    def hw_acceleration(self) -> str:
        return str(self._s.value("player/hw_acceleration", "auto"))

    @hw_acceleration.setter
    def hw_acceleration(self, value: str) -> None:
        self._s.setValue("player/hw_acceleration", value)

    @property
    def audio_boost(self) -> str:
        return str(self._s.value("player/audio_boost", "off"))

    @audio_boost.setter
    def audio_boost(self, value: str) -> None:
        self._s.setValue("player/audio_boost", value)

    @property
    def default_aspect(self) -> str:
        return str(self._s.value("player/default_aspect", "auto"))

    @default_aspect.setter
    def default_aspect(self, value: str) -> None:
        self._s.setValue("player/default_aspect", value)

    @property
    def external_player(self) -> str:
        return str(self._s.value("player/external_player", "vlc"))

    @external_player.setter
    def external_player(self, value: str) -> None:
        self._s.setValue("player/external_player", value)

    @property
    def external_player_path(self) -> str:
        return str(self._s.value("player/external_player_path", ""))

    @external_player_path.setter
    def external_player_path(self, value: str) -> None:
        self._s.setValue("player/external_player_path", value)

    @property
    def user_agent(self) -> str:
        return str(self._s.value("network/user_agent", "NovaIPTV/2.0"))

    @user_agent.setter
    def user_agent(self, value: str) -> None:
        self._s.setValue("network/user_agent", value)

    @property
    def record_directory(self) -> str:
        return str(self._s.value("record/directory", ""))

    @record_directory.setter
    def record_directory(self, value: str) -> None:
        self._s.setValue("record/directory", value)

    def save(self) -> None:
        self.sync()

    def sync(self) -> None:
        self._s.sync()
