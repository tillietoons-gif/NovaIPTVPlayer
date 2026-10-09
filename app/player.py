"""VLC playback controller.

Embedding notes (the tricky part):
- python-vlc must match the installed VLC bitness: on 64-bit Windows you
  need 64-bit VLC *and* 64-bit Python, otherwise ``import vlc`` fails.
  On Linux, install VLC via your package manager (e.g. ``sudo apt install vlc``).
- The video output must be told which native window to draw into *before*
  playback starts. On Windows that is ``media_player.set_hwnd(hwnd)``,
  on Linux ``media_player.set_xwindow(xid)`` where the id comes from
  ``QWidget.winId()``.
- On Linux/Wayland, VLC embedding works best under XWayland: if you get a
  black video, run with ``QT_QPA_PLATFORM=xcb`` to force X11.
- The target widget must already be realized (shown at least once) when
  ``attach()`` is called, otherwise the handle is invalid and you get a
  black rectangle. We re-attach on every play() call to be safe.
- Keep a strong reference to the vlc.Instance / Media / MediaPlayer objects
  for the whole app lifetime; letting them get garbage-collected stops
  playback abruptly.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal, QTimer

try:
    import vlc
    _VLC_AVAILABLE = True
    _VLC_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on host VLC install
    vlc = None  # type: ignore[assignment]
    _VLC_AVAILABLE = False
    _VLC_IMPORT_ERROR = exc


class VlcPlayer(QObject):
    """Thin Qt-friendly wrapper around libvlc's MediaPlayer."""

    state_changed = Signal(str)   # playing | paused | stopped | error | buffering
    position_changed = Signal(int, int)  # time_ms, duration_ms

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._instance = None
        self._player = None
        self._media = None
        self._widget = None
        self._current_url = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll_position)

        if _VLC_AVAILABLE:
            # --network-caching keeps HLS/RTSP zappy without over-buffering.
            self._instance = vlc.Instance(
                "--no-video-title-show",
                "--network-caching=1500",
            )
            self._player = self._instance.media_player_new()
            events = self._player.event_manager()
            events.event_attach(
                vlc.EventType.MediaPlayerPlaying, lambda e: self.state_changed.emit("playing")
            )
            events.event_attach(
                vlc.EventType.MediaPlayerPaused, lambda e: self.state_changed.emit("paused")
            )
            events.event_attach(
                vlc.EventType.MediaPlayerStopped, lambda e: self.state_changed.emit("stopped")
            )
            events.event_attach(
                vlc.EventType.MediaPlayerEncounteredError,
                lambda e: self.state_changed.emit("error"),
            )
            events.event_attach(
                vlc.EventType.MediaPlayerBuffering, lambda e: self.state_changed.emit("buffering")
            )

    # -- setup ------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        return _VLC_AVAILABLE

    @staticmethod
    def import_error() -> Exception | None:
        return _VLC_IMPORT_ERROR

    def attach(self, widget) -> None:
        """Bind video output to a QWidget. Call after the widget is shown."""
        self._widget = widget
        if not _VLC_AVAILABLE or widget is None:
            return
        hwnd = int(widget.winId())
        if sys.platform.startswith("win"):
            self._player.set_hwnd(hwnd)
        elif sys.platform.startswith("linux"):
            self._player.set_xwindow(hwnd)
        elif sys.platform == "darwin":
            self._player.set_nsobject(hwnd)

    # -- transport --------------------------------------------------------
    def play(self, url: str) -> None:
        if not _VLC_AVAILABLE:
            self.state_changed.emit("error")
            return
        self.stop()
        self._current_url = url
        if self._widget is not None:
            self.attach(self._widget)  # re-attach: handle may have changed
        self._media = self._instance.media_new(url)
        # Hint for live HLS/DASH streams.
        self._media.add_option(":http-reconnect")
        self._player.set_media(self._media)
        self._player.play()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        if _VLC_AVAILABLE and self._player is not None:
            self._player.stop()
        self._timer.stop()
        self.position_changed.emit(0, 0)

    def toggle_pause(self) -> None:
        if _VLC_AVAILABLE and self._player is not None:
            self._player.pause()

    @property
    def current_url(self) -> str:
        return self._current_url

    # -- audio ------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        volume = max(0, min(125, volume))
        if _VLC_AVAILABLE and self._player is not None:
            self._player.audio_set_volume(volume)

    def set_mute(self, muted: bool) -> None:
        if _VLC_AVAILABLE and self._player is not None:
            self._player.audio_set_mute(1 if muted else 0)

    # -- internals --------------------------------------------------------
    def _poll_position(self) -> None:
        if not _VLC_AVAILABLE or self._player is None:
            return
        try:
            t = self._player.get_time()
            d = self._player.get_length()
            self.position_changed.emit(max(0, t), max(0, d))
        except Exception:
            pass
