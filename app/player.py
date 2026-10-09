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
    recording_started = Signal(str)  # path
    recording_stopped = Signal(str)  # final path
    recording_error = Signal(str)    # human-readable failure reason
    ended = Signal()                 # natural end of stream (not user stop)
    tracks_ready = Signal(list, list)  # audio_tracks, subtitle_tracks
    subtitle_ready = Signal(str)        # subtitle text

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
        self._last_shown_pts: float | None = None  # newest presented video pts
        self.error_detail: str = ""  # first failure description, if any
        self.seekable = False        # True once a finite duration is known
        self._target_audio_index: int | None = None
        self._target_sub_index: int | None = None
        self._current_audio_index: int | None = None
        self._current_sub_index: int | None = None
        # recording state (plain attributes polled from the GUI thread)
        self._rec_request: str | None = None  # pending start request
        self._rec_stop = False                # pending stop request
        self._rec_out = None                  # open av output container
        self._rec_map: dict = {}              # input stream -> output stream
        self._rec_path: str | None = None     # path of the active recording

    # -- control (called from the GUI thread) --------------------------------
    def request_audio_track(self, index: int) -> None:
        self._target_audio_index = int(index)

    def request_subtitle_track(self, index: int | None) -> None:
        self._target_sub_index = int(index) if index is not None else None

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

    def request_recording(self, path: str) -> None:
        """Start remuxing the stream to *path* (no re-encode)."""
        self._rec_request = path
        self._rec_stop = False

    def request_stop_recording(self) -> str | None:
        """Ask the worker to finalize the recording; returns its path."""
        path = self._rec_path
        self._rec_request = None  # cancel a not-yet-started recording too
        self._rec_stop = True
        return path

    @property
    def is_recording(self) -> bool:
        return self._rec_out is not None or self._rec_request is not None

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(125, int(volume)))

    def set_mute(self, muted: bool) -> None:
        self._muted = bool(muted)

    # -- worker ---------------------------------------------------------------
    def run(self) -> None:  # noqa: C901 - the decode loop is inherently long
        try:
            container = av.open(
                self.url, options=_open_options(self.url, self.headers))
        except Exception as exc:
            self.error_detail = f"Could not open stream: {exc}"
            self.state_changed.emit("error")
            return

        try:
            self._decode_loop(container)
        except Exception as exc:
            # Any decode failure (codec missing, stream died, ...) -> error.
            if not self.error_detail:
                self.error_detail = f"Decode failed: {exc}"
            self.state_changed.emit("error")
        finally:
            self._close_recording()  # finalize a recording on any exit path
            try:
                container.close()
            except Exception:
                pass

    def _decode_loop(self, container) -> None:
        # Pick streams: biggest video, first audio; either may be missing.
        vstreams = [s for s in container.streams if s.type == "video"]
        astreams = [s for s in container.streams if s.type == "audio"]
        substreams = [s for s in container.streams if s.type == "subtitle"]

        audio_tracks = []
        for s in astreams:
            meta = getattr(s, "metadata", {}) or {}
            lang = meta.get("language", "und")
            title = meta.get("title", "")
            codec = getattr(s.codec_context, "name", "") if hasattr(s, "codec_context") else ""
            audio_tracks.append({"index": s.index, "language": lang, "title": title, "codec": codec})

        subtitle_tracks = []
        for s in substreams:
            meta = getattr(s, "metadata", {}) or {}
            lang = meta.get("language", "und")
            title = meta.get("title", "")
            subtitle_tracks.append({"index": s.index, "language": lang, "title": title})

        self.tracks_ready.emit(audio_tracks, subtitle_tracks)

        vstream = (max(vstreams, key=lambda s: (s.width or 0) * (s.height or 0))
                   if vstreams else None)
        astream = astreams[0] if astreams else None
        if astream is not None:
            self._current_audio_index = astream.index
        substream = None
        if vstream is None and astream is None:
            self.error_detail = "No audio/video streams found in the URL"
            self.state_changed.emit("error")
            return

        try:
            duration_ms = max(0, int(container.duration // 1000))
        except Exception:
            duration_ms = 0  # live streams report no duration
        self.seekable = duration_ms > 0

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

        streams = [s for s in (vstream, *astreams, *substreams) if s is not None]
        self.state_changed.emit("buffering")

        t0: float | None = None       # wall clock anchored to pts_origin
        pts_origin: float | None = None
        stream_pts_start: float | None = None
        position_s = 0.0
        got_first = False
        last_report = 0.0
        last_vol = self._effective_volume()

        for packet in container.demux(*streams):
            if self._stop_event.is_set():
                break

            # -- audio track switch request ----------------------------------
            if (self._target_audio_index is not None
                    and self._target_audio_index != self._current_audio_index):
                target = next((s for s in astreams if s.index == self._target_audio_index), None)
                if target is not None:
                    astream = target
                    self._current_audio_index = astream.index
                    try:
                        resampler = av.AudioResampler(format="s16", layout="stereo", rate=_AUDIO_RATE)
                        if sink is not None:
                            sink.reset()
                    except Exception:
                        pass

            # -- subtitle track switch request -------------------------------
            if self._target_sub_index != self._current_sub_index:
                self._current_sub_index = self._target_sub_index
                substream = next((s for s in substreams if s.index == self._target_sub_index), None)
                if substream is None:
                    self.subtitle_ready.emit("")

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
                    self._last_shown_pts = None     # forget presented history
                    position_s = ms / 1000.0
                    if sink is not None:
                        sink.reset()
                    self._close_recording(
                        "Recording stopped: seeking is not supported "
                        "while recording.")
                except Exception:
                    pass

            # -- recording: open the output on request, mux each packet ------
            if self._rec_stop:
                self._rec_stop = False
                self._close_recording()
            self._maybe_start_recording(vstream, astream)

            # Subtitle packet handling
            if substream is not None and packet.stream == substream:
                try:
                    for sub in packet.decode():
                        txt = getattr(sub, "text", "")
                        if not txt and hasattr(sub, "rects"):
                            txt = " ".join(r.text for r in sub.rects if hasattr(r, "text") and r.text)
                        if txt:
                            self.subtitle_ready.emit(txt)
                except Exception:
                    pass
                continue

            # Only decode active video and audio streams
            if packet.stream not in (vstream, astream):
                continue

            try:
                frames = list(packet.decode())
            except Exception:
                continue  # a corrupt packet must not kill playback
            if self._rec_out is not None:
                self._mux_packet(packet)

            for frame in frames:
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
                if stream_pts_start is None:
                    stream_pts_start = pts

                # Discontinuity detection (PTS reset, jump or HLS cut): re-anchor clock
                if (self._last_shown_pts is not None
                        and abs(pts - self._last_shown_pts) > 1.5):
                    pts_origin = pts
                    t0 = time.monotonic()
                    self._last_shown_pts = None
                elif pts_origin is None:  # anchor the clock on the first frame
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
                    if stream_pts_start is not None and duration_ms > 0:
                        pos_ms = max(0, int((position_s - stream_pts_start) * 1000))
                    else:
                        pos_ms = max(0, int((position_s - pts_origin) * 1000))
                    self.position_changed.emit(pos_ms, duration_ms)

        # Natural end of stream (or stop): release the audio device.
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass
        if not self._stop_event.is_set():
            self._close_recording()  # finalize any recording first
            self.ended.emit()        # natural end (not a user stop)
            self.state_changed.emit("stopped")

    # -- recording (remux, no re-encode) ------------------------------------------
    def _maybe_start_recording(self, vstream, astream) -> None:
        """Open the MP4 output on a pending start request (worker thread)."""
        if self._rec_out is not None or self._rec_request is None:
            return
        path, self._rec_request = self._rec_request, None
        try:
            out = av.open(path, "w", format="mp4")
            mapping: dict = {}
            if vstream is not None:
                mapping[vstream] = out.add_stream(template=vstream)
            if astream is not None:
                mapping[astream] = out.add_stream(template=astream)
            if not mapping:
                raise RuntimeError("no streams to record")
            if hasattr(out, "start_writing"):
                out.start_writing()
            self._rec_out = out
            self._rec_map = mapping
            self._rec_path = path
        except Exception as exc:
            self._close_recording()  # defensive: never leave a half-open file
            self.recording_error.emit(f"Could not start recording: {exc}")
            return
        self.recording_started.emit(path)

    def _mux_packet(self, packet) -> None:
        """Write one demuxed packet to the recording (worker thread)."""
        out_stream = self._rec_map.get(packet.stream)
        if out_stream is None:
            return
        if packet.dts is None:
            return  # can't mux without a timestamp; skip gracefully
        try:
            packet.stream = out_stream  # route to the output stream
            self._rec_out.mux(packet)
        except Exception as exc:
            # Recording must never kill playback: finalize what we have.
            self._close_recording(f"Recording failed: {exc}")

    def _close_recording(self, error: str | None = None) -> None:
        """Finalize the recording file (worker thread). Emits signals."""
        out, self._rec_out = self._rec_out, None
        self._rec_map = {}
        path, self._rec_path = self._rec_path, None
        if out is None:
            return
        try:
            out.close()  # writes the MP4 trailer
        except Exception:
            pass
        if path:
            if error:
                self.recording_error.emit(error)
            self.recording_stopped.emit(path)

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
        """Pace, convert and emit one video frame. Returns True if shown.

        Staleness is judged against the newest *presented* pts, not the
        wall clock: audio/video packets are often interleaved unevenly, so
        a frame decoded "late" by the clock may still be the newest picture
        we have and must be shown (it catches up instantly). Only frames
        older than what is already on screen are dropped.
        """
        if (self._last_shown_pts is not None
                and pts < self._last_shown_pts - _LATE_DROP_S):
            return False  # stale: a newer picture is already on screen
        self._pace(pts, t0, pts_origin)
        if self._stop_event.is_set() or self._seek_ms is not None:
            return False
        try:
            rgb = frame.reformat(format="rgb24") if frame.format.name != "rgb24" else frame
            plane = rgb.planes[0]
            # QImage wraps the buffer WITHOUT copying; .copy() detaches it
            # so the decoder can safely reuse the buffer for the next frame.
            img = QImage(memoryview(plane), rgb.width, rgb.height,
                         plane.line_size, QImage.Format_RGB888).copy()
        except Exception:
            return False
        if img.isNull():
            return False
        self.frame_ready.emit(img)
        self._last_shown_pts = pts
        return True

    def _write_audio(self, frame, resampler, device) -> None:
        """Resample to s16/stereo/44.1k and push PCM in ~8 KB chunks."""
        try:
            for af in resampler.resample(frame):
                data = bytes(af.planes[0])
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
    tracks_ready = Signal(list, list)  # audio_tracks, subtitle_tracks
    subtitle_ready = Signal(str)      # current subtitle text
    recording_started = Signal(str)  # path
    recording_stopped = Signal(str)  # final path
    recording_error = Signal(str)    # human-readable failure reason
    playback_finished = Signal()     # natural end of stream (not user stop)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: _DecodeWorker | None = None
        self._worker_connections: list = []
        self._zombies: list[_DecodeWorker] = []  # stuck workers dying on their own
        self._widget = None           # target VideoWidget (no native handles)
        self._volume = 80
        self._muted = False
        self._current_url = ""
        self._last_error = ""         # human-readable reason for last failure
        self._last_pos_s = 0.0        # last reported position, seconds
        self._last_dur_s: float | None = None  # last reported duration, s
        self._audio_tracks: list[dict] = []
        self._subtitle_tracks: list[dict] = []
        self._current_audio_track: int = 0
        self._current_subtitle_track: int = -1

    # -- setup ------------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        return _AV_AVAILABLE

    @staticmethod
    def import_error() -> Exception | None:
        return _AV_IMPORT_ERROR

    def attach(self, widget) -> None:
        """Remember the target video widget and hook subtitle delivery."""
        if self._widget is not None and hasattr(self._widget, "set_subtitle"):
            try:
                self.subtitle_ready.disconnect(self._widget.set_subtitle)
            except (RuntimeError, TypeError):
                pass
        self._widget = widget
        if self._widget is not None and hasattr(self._widget, "set_subtitle"):
            self.subtitle_ready.connect(self._widget.set_subtitle)

    # -- transport ----------------------------------------------------------------
    def play(self, url: str,
             headers: dict[str, str] | None = None) -> None:
        if not _AV_AVAILABLE:
            self._last_error = (
                "Video engine could not be loaded. "
                + (str(_AV_IMPORT_ERROR) if _AV_IMPORT_ERROR else
                   "Reinstall the app or run: pip install av"))
            self.state_changed.emit("error")
            return
        self.stop()  # tear down any previous stream first
        self._current_url = url
        self._last_error = ""
        self._last_pos_s = 0.0
        self._last_dur_s = None
        self._audio_tracks = []
        self._subtitle_tracks = []
        self._current_audio_track = 0
        self._current_subtitle_track = -1
        self._worker = _DecodeWorker(
            url, self._volume, self._muted, dict(headers or {}))
        # Signal-to-signal chaining is thread-safe: Qt queues the hop.
        self._worker_connections = [
            self._worker.frame_ready.connect(self.frame_ready.emit),
            self._worker.state_changed.connect(self.state_changed.emit),
            self._worker.state_changed.connect(self._capture_worker_error),
            self._worker.position_changed.connect(self.position_changed.emit),
            self._worker.position_changed.connect(self._track_position),
            self._worker.tracks_ready.connect(self._on_tracks_ready),
            self._worker.subtitle_ready.connect(self.subtitle_ready.emit),
            self._worker.recording_started.connect(self.recording_started.emit),
            self._worker.recording_stopped.connect(self.recording_stopped.emit),
            self._worker.recording_error.connect(self.recording_error.emit),
            self._worker.ended.connect(self.playback_finished.emit),
        ]
        self._worker.start()

    def _on_tracks_ready(self, audio: list, subs: list) -> None:
        self._audio_tracks = audio
        self._subtitle_tracks = subs
        if audio:
            self._current_audio_track = audio[0].get("index", 0)
        self._current_subtitle_track = -1
        self.tracks_ready.emit(audio, subs)

    def _track_position(self, pos_ms: int, dur_ms: int) -> None:
        self._last_pos_s = max(0.0, pos_ms / 1000.0)
        self._last_dur_s = dur_ms / 1000.0 if dur_ms > 0 else None

    def _capture_worker_error(self, state: str) -> None:
        """Remember the worker's failure reason for the error dialog."""
        if state == "error" and self._worker is not None:
            detail = (self._worker.error_detail or "").strip()
            if detail:
                self._last_error = detail

    @property
    def last_error(self) -> str:
        """Human-readable reason for the most recent playback failure."""
        return self._last_error

    def stop(self) -> None:
        self.stop_recording()  # finalize any recording first
        for conn in getattr(self, "_worker_connections", []):
            try:
                QObject.disconnect(conn)
            except (RuntimeError, TypeError):
                pass
        self._worker_connections = []
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
        if self._widget is not None:
            if hasattr(self._widget, "clear"):
                self._widget.clear()
            if hasattr(self._widget, "set_subtitle"):
                self._widget.set_subtitle("")

    def toggle_pause(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.toggle_pause()

    def seek(self, seconds: float) -> bool:
        """Seek VOD streams. Returns False for live/unseekable streams.

        Live channels are never seek-disturbed: the request is refused
        instead of being sent to the worker.
        """
        worker = self._worker
        if worker is None or not worker.isRunning():
            return False
        if not worker.seekable:
            return False
        worker.request_seek(int(max(0.0, seconds) * 1000))
        return True

    @property
    def current_url(self) -> str:
        return self._current_url

    def position(self) -> float:
        """Seconds into the current stream (0.0 if unknown)."""
        return self._last_pos_s

    def duration(self) -> float | None:
        """Stream duration in seconds, or None for live/unknown."""
        return self._last_dur_s

    # -- recording ------------------------------------------------------------------
    def start_recording(self, path: str) -> None:
        """Begin remuxing the current stream to *path* (MP4, no re-encode)."""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_recording(path)
        else:
            self.recording_error.emit("Nothing is playing to record.")

    def stop_recording(self) -> str | None:
        """Finalize the active recording; returns its path (or None)."""
        worker = self._worker
        if worker is not None and worker.isRunning():
            return worker.request_stop_recording()
        return None

    @property
    def is_recording(self) -> bool:
        worker = self._worker
        return bool(worker is not None and worker.isRunning()
                    and worker.is_recording)

    # -- audio ----------------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(125, int(volume)))
        if self._worker is not None:
            self._worker.set_volume(self._volume)

    def set_mute(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._worker is not None:
            self._worker.set_mute(self._muted)

    # -- tracks & subtitles ---------------------------------------------------------
    def audio_tracks(self) -> list[dict]:
        """Return list of available audio tracks with metadata."""
        return list(self._audio_tracks)

    def subtitle_tracks(self) -> list[dict]:
        """Return list of available subtitle tracks with metadata."""
        return list(self._subtitle_tracks)

    def set_audio_track(self, index: int) -> None:
        """Switch audio track by stream index."""
        self._current_audio_track = index
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_audio_track(index)

    def set_subtitle_track(self, index: int | None) -> None:
        """Switch subtitle track by stream index, or None / -1 to disable."""
        sub_idx = index if index is not None and index >= 0 else None
        self._current_subtitle_track = sub_idx if sub_idx is not None else -1
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_subtitle_track(sub_idx)
        if sub_idx is None and self._widget is not None and hasattr(self._widget, "set_subtitle"):
            self._widget.set_subtitle("")

    @property
    def current_audio_track(self) -> int:
        return self._current_audio_track

    @property
    def current_subtitle_track(self) -> int:
        return self._current_subtitle_track
