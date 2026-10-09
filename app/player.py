"""Self-contained media player engine (no VLC required).

Pipeline overview
-----------------
URL -> PyAV (bundled FFmpeg) demux + decode -> QThread worker
  video: AVFrame -> rgb24 ndarray -> QImage -> ``frame_ready`` -> VideoWidget
  audio: AVFrame -> AudioResampler(s16/stereo/44100) -> PCM -> QAudioSink

Why PyAV: its pip wheels bundle the FFmpeg libraries, so the app plays
HLS / DASH / RTSP / MP4 with zero system dependencies -- no VLC install
and no system FFmpeg needed on Windows or Linux.

Threading notes (the tricky parts)
----------------------------------
* All demux/decode/audio I/O happens in :class:`_DecodeWorker` (a QThread);
  the GUI thread never blocks on the network.
* ``QImage`` wraps the numpy pixel buffer *without copying*, and the
  decoder reuses that buffer for the next frame -- so we MUST call
  ``.copy()`` before emitting the image across threads, otherwise the
  widget can paint a half-overwritten frame (or worse).
* A/V sync: video frames are paced against the wall clock anchored to the
  first frame's pts. Frames more than ~0.4 s late are dropped; early frames
  sleep in <=50 ms slices so stop/pause/seek stay responsive. Audio (when
  present) is the position master.
* ``QAudioSink`` is created *inside* the worker thread so every audio call
  keeps the right thread affinity. Volume/mute/seek are plain attributes
  polled each loop iteration (single-assignment is GIL-atomic; no locks).
* Pause keeps the container open and suspends the audio sink; on resume the
  wall-clock anchor is shifted by the paused duration so playback continues
  seamlessly instead of jumping.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioFormat, QAudioSink

try:
    import av
    _AV_AVAILABLE = True
    _AV_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on installed packages
    av = None  # type: ignore[assignment]
    _AV_AVAILABLE = False
    _AV_IMPORT_ERROR = exc

# Network read timeout for av.open, in microseconds (15 s).
_RW_TIMEOUT_US = "15000000"
# Drop video frames this far behind schedule; sleep granularity for pacing.
_LATE_DROP_S = 0.4
_SLEEP_SLICE_S = 0.05
# Audio target format fed to QAudioSink.
_AUDIO_RATE = 44100
_AUDIO_CHANNELS = 2
_AUDIO_CHUNK = 8192  # bytes per QIODevice write


def _open_options(url: str, stream_headers: dict[str, str]) -> dict[str, str]:
    """Build FFmpeg options, including HTTP compatibility for live streams."""
    options = {"rw_timeout": _RW_TIMEOUT_US}
    if urlsplit(url).scheme.lower() in ("http", "https"):
        headers = {key.lower(): value for key, value in stream_headers.items()}
        options.update({
            "user_agent": headers.get("user-agent", "NovaIPTV/1.0"),
            "reconnect": "1",
            "reconnect_streamed": "1",
            "reconnect_delay_max": "5",
        })
        if "referer" in headers:
            options["referer"] = headers["referer"]
    return options


def _pts_seconds(frame) -> float | None:
    """Frame presentation timestamp in seconds, or None if unknown."""
    if frame.pts is None:
        return None
    return float(frame.pts * frame.time_base)


class _DecodeWorker(QThread):
    """Demuxes + decodes one stream in the background.

    Emits ``frame_ready`` (video), ``state_changed`` and ``position_changed``.
    All Qt-multimedia objects it touches are created in ``run()`` so they
    live in this thread.
    """

    frame_ready = Signal(QImage)
    state_changed = Signal(str)      # playing | paused | stopped | error | buffering
    position_changed = Signal(int, int)  # position_ms, duration_ms

    def __init__(self, url: str, volume: int, muted: bool,
                 headers: dict[str, str] | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.url = url
        self.headers = headers or {}
        self._volume = volume          # 0..125, polled from GUI thread
        self._muted = muted            # polled from GUI thread
        self._stop_event = threading.Event()
        self._paused = False
        self._pause_cond = threading.Condition()
        self._seek_ms: int | None = None  # pending seek request (polled)

    # -- control (called from the GUI thread) --------------------------------
    def request_stop(self) -> None:
        self._stop_event.set()
        with self._pause_cond:
            self._paused = False
            self._pause_cond.notify_all()

    def toggle_pause(self) -> None:
        with self._pause_cond:
            self._paused = not self._paused
            self._pause_cond.notify_all()

    def request_seek(self, ms: int) -> None:
        self._seek_ms = max(0, int(ms))

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(125, int(volume)))

    def set_mute(self, muted: bool) -> None:
        self._muted = bool(muted)

    # -- worker ---------------------------------------------------------------
    def run(self) -> None:  # noqa: C901 - the decode loop is inherently long
        try:
            container = av.open(
                self.url, options=_open_options(self.url, self.headers))
        except Exception:
            self.state_changed.emit("error")
            return

        try:
            self._decode_loop(container)
        except Exception:
            # Any decode failure (codec missing, stream died, ...) -> error.
            self.state_changed.emit("error")
        finally:
            try:
                container.close()
            except Exception:
                pass

    def _decode_loop(self, container) -> None:
        # Pick streams: biggest video, first audio; either may be missing.
        vstreams = [s for s in container.streams if s.type == "video"]
        astreams = [s for s in container.streams if s.type == "audio"]
        vstream = (max(vstreams, key=lambda s: (s.width or 0) * (s.height or 0))
                   if vstreams else None)
        astream = astreams[0] if astreams else None
        if vstream is None and astream is None:
            self.state_changed.emit("error")
            return

        try:
            duration_ms = max(0, int(container.duration // 1000))
        except Exception:
            duration_ms = 0  # live streams report no duration

        # Audio output chain (created in this thread for correct affinity).
        sink: QAudioSink | None = None
        device = None
        resampler = None
        if astream is not None:
            try:
                fmt = QAudioFormat()
                fmt.setSampleRate(_AUDIO_RATE)
                fmt.setChannelCount(_AUDIO_CHANNELS)
                fmt.setSampleFormat(QAudioFormat.Int16)
                sink = QAudioSink(fmt)  # default output device
                sink.setVolume(self._effective_volume())
                device = sink.start()
                resampler = av.AudioResampler(format="s16", layout="stereo",
                                              rate=_AUDIO_RATE)
            except Exception:
                sink, device, resampler = None, None, None

        streams = [s for s in (vstream, astream) if s is not None]
        self.state_changed.emit("buffering")

        t0: float | None = None       # wall clock anchored to pts_origin
        pts_origin: float | None = None
        position_s = 0.0
        got_first = False
        last_report = 0.0
        last_vol = self._effective_volume()

        for frame in container.decode(*streams):
            if self._stop_event.is_set():
                break

            # -- pause: wait with the container open, audio suspended --------
            with self._pause_cond:
                if self._paused:
                    pause_started = time.monotonic()
                    if sink is not None:
                        try:
                            sink.suspend()
                        except Exception:
                            pass
                    self.state_changed.emit("paused")
                    while self._paused and not self._stop_event.is_set():
                        self._pause_cond.wait(timeout=0.05)
                    if sink is not None:
                        try:
                            sink.resume()
                        except Exception:
                            pass
                    if t0 is not None:  # shift anchor: no jump on resume
                        t0 += time.monotonic() - pause_started
                    if not self._stop_event.is_set():
                        self.state_changed.emit("playing")
            if self._stop_event.is_set():
                break

            # -- pending seek (VOD; live streams raise -> ignored) -----------
            if self._seek_ms is not None:
                ms, self._seek_ms = self._seek_ms, None
                try:
                    container.seek(int(ms * 1000))  # AV_TIME_BASE = µs
                    t0, pts_origin = None, None     # re-anchor on next frame
                    if sink is not None:
                        sink.reset()
                except Exception:
                    pass  # live/unsupported: keep playing from current point

            # -- live volume/mute changes ------------------------------------
            vol = self._effective_volume()
            if sink is not None and vol != last_vol:
                try:
                    sink.setVolume(vol)
                except Exception:
                    pass
                last_vol = vol

            pts = _pts_seconds(frame)
            if pts is None:
                continue
            if pts_origin is None:  # anchor the clock on the first frame
                pts_origin = pts
                t0 = time.monotonic()
            if not got_first:
                got_first = True
                self.state_changed.emit("playing")
            assert t0 is not None

            if isinstance(frame, av.VideoFrame):
                if self._handle_video(frame, pts, t0, pts_origin):
                    position_s = max(position_s, pts)
            elif isinstance(frame, av.AudioFrame):
                if sink is not None and device is not None and resampler is not None:
                    self._pace(pts, t0, pts_origin)
                    if self._stop_event.is_set() or self._seek_ms is not None:
                        continue
                    self._write_audio(frame, resampler, device)
                    position_s = max(position_s, pts)

            now = time.monotonic()
            if now - last_report >= 1.0 and pts_origin is not None:
                last_report = now
                pos_ms = max(0, int((position_s - pts_origin) * 1000))
                self.position_changed.emit(pos_ms, duration_ms)

        # Natural end of stream (or stop): release the audio device.
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass
        if not self._stop_event.is_set():
            self.state_changed.emit("stopped")

    # -- helpers ----------------------------------------------------------------
    def _effective_volume(self) -> float:
        if self._muted:
            return 0.0
        return max(0.0, min(1.0, self._volume / 100.0))

    def _pace(self, pts: float, t0: float, pts_origin: float) -> None:
        """Sleep until a frame's pts is due (<=50 ms slices)."""
        due = t0 + (pts - pts_origin)
        while True:
            if self._stop_event.is_set() or self._paused or self._seek_ms is not None:
                return
            remaining = due - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(_SLEEP_SLICE_S, remaining))

    def _handle_video(self, frame, pts: float, t0: float,
                      pts_origin: float) -> bool:
        """Pace, convert and emit one video frame. Returns True if shown."""
        due = t0 + (pts - pts_origin)
        if due < time.monotonic() - _LATE_DROP_S:
            return False  # too late: drop it, don't bunch up
        self._pace(pts, t0, pts_origin)
        if self._stop_event.is_set() or self._seek_ms is not None:
            return False
        try:
            arr = frame.to_ndarray(format="rgb24")
        except Exception:
            return False
        h, w = int(arr.shape[0]), int(arr.shape[1])
        # QImage wraps the numpy buffer WITHOUT copying; .copy() detaches it
        # so the decoder can safely reuse the buffer for the next frame.
        img = QImage(arr.data, w, h, 3 * w,
                     QImage.Format_RGB888).copy()
        if img.isNull():
            return False
        self.frame_ready.emit(img)
        return True

    def _write_audio(self, frame, resampler, device) -> None:
        """Resample to s16/stereo/44.1k and push PCM in ~8 KB chunks."""
        try:
            for af in resampler.resample(frame):
                data = bytes(af.to_ndarray())
                off = 0
                while off < len(data):
                    if self._stop_event.is_set():
                        return
                    n = device.write(data[off:off + _AUDIO_CHUNK])
                    if n is None or n < 0:
                        return
                    if n == 0:
                        time.sleep(0.01)  # device buffer full; yield briefly
                        continue
                    off += n
        except Exception:
            pass  # a glitchy audio packet must not kill video


class Player(QObject):
    """Self-contained playback controller (PyAV decode, Qt audio/video).

    Drop-in replacement for the old VLC wrapper: same public API and
    signals, plus ``frame_ready(QImage)`` carrying decoded video frames
    for :class:`ui.widgets.VideoWidget`.
    """

    state_changed = Signal(str)       # playing | paused | stopped | error | buffering
    position_changed = Signal(int, int)  # position_ms, duration_ms
    frame_ready = Signal(QImage)      # decoded video frame (already copied)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: _DecodeWorker | None = None
        self._zombies: list[_DecodeWorker] = []  # stuck workers dying on their own
        self._widget = None           # target VideoWidget (no native handles)
        self._volume = 80
        self._muted = False
        self._current_url = ""

    # -- setup ------------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        return _AV_AVAILABLE

    @staticmethod
    def import_error() -> Exception | None:
        return _AV_IMPORT_ERROR

    def attach(self, widget) -> None:
        """Remember the target video widget. No native handles involved."""
        self._widget = widget

    # -- transport ----------------------------------------------------------------
    def play(self, url: str,
             headers: dict[str, str] | None = None) -> None:
        if not _AV_AVAILABLE:
            self.state_changed.emit("error")
            return
        self.stop()  # tear down any previous stream first
        self._current_url = url
        self._worker = _DecodeWorker(
            url, self._volume, self._muted, dict(headers or {}))
        # Signal-to-signal chaining is thread-safe: Qt queues the hop.
        self._worker.frame_ready.connect(self.frame_ready.emit)
        self._worker.state_changed.connect(self.state_changed.emit)
        self._worker.position_changed.connect(self.position_changed.emit)
        self._worker.start()

    def stop(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.request_stop()
            if not worker.wait(5000):
                # Stream stuck inside a blocking network read (bounded by the
                # 15 s rw_timeout). Never destroy a running QThread: park it
                # and let it clean itself up when the read finally unblocks.
                self._zombies.append(worker)
                worker.finished.connect(worker.deleteLater)
                worker.finished.connect(
                    lambda w=worker: self._zombies.remove(w)
                    if w in self._zombies else None)
        self.state_changed.emit("stopped")
        self.position_changed.emit(0, 0)
        if self._widget is not None and hasattr(self._widget, "clear"):
            self._widget.clear()

    def toggle_pause(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.toggle_pause()

    def seek(self, ms: int) -> None:
        """Seek VOD streams; silently ignored for live streams."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_seek(ms)

    @property
    def current_url(self) -> str:
        return self._current_url

    # -- audio ----------------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(125, int(volume)))
        if self._worker is not None:
            self._worker.set_volume(self._volume)

    def set_mute(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._worker is not None:
            self._worker.set_mute(self._muted)
