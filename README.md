# ⚡ Nova IPTV Player

An advanced IPTV player for **Windows and Linux** with a modern dark UI, built with
**PySide6 (Qt6)** and a **self-contained player engine** — it decodes HLS / DASH /
RTSP / MP4 with bundled FFmpeg via PyAV, so there is **nothing else to install**
(no VLC, no system FFmpeg).

Features:

- 📡 Load M3U/M3U8 playlists from **file or URL** (Xtream-style `#EXTINF` with `tvg-id`, `tvg-logo`, `group-title`)
- 🎬 Automatic **Live TV / Movies / Series** classification + category filter + instant search
- 🗓 **XMLTV EPG** support: now/next on every card, 6-hour timeline guide
- ⭐ **Favorites** persisted to JSON, toggle with the star on any card
- 🕘 **Recent history** with double-click replay
- 🔊 Volume slider, mute, pause/resume, stop, fullscreen video
- 🌙 Dark glassy theme with a violet `#8b5cf6` accent, async logo loading

## ⬇️ Download (Windows)

Every push to `main` builds a standalone Windows `.exe` via [GitHub Actions](../../actions/workflows/main.yml) —
download `NovaIPTVPlayer.exe` from the latest run's `NovaIPTVPlayer-windows`
artifact. Pushing a version tag such as `v1.0.0` also creates a GitHub Release
with the executable attached. Just download and run it — no install needed
(the FFmpeg decoder is bundled inside).

## Requirements

| # | Requirement | Windows | Linux |
|---|-------------|---------|-------|
| 1 | OS 64-bit | Windows 10/11 | Ubuntu 22.04+ / Fedora / Arch (any modern distro) |
| 2 | Python 3.10+ 64-bit | From python.org or the Microsoft Store | From distro or python.org |

That's it — video/audio decoding ships inside the `av` (PyAV) pip wheel,
which bundles the FFmpeg libraries. No VLC, no system FFmpeg, no codec packs.

## Setup (Windows)

```powershell
# 1. Install dependencies
cd iptv-player
pip install -r requirements.txt

# 2. Run
python main.py
```

## Setup (Linux)

```bash
# 1. Install dependencies (Debian/Ubuntu example)
sudo apt update
sudo apt install python3-pip
pip install -r requirements.txt

# 2. Run
python3 main.py
# or use the helper script:
# ./run.sh
```

## Usage

1. Click **＋ Playlist** (top right).
2. Paste your **M3U/M3U8 URL** (or pick a local `.m3u` file) and optionally an **XMLTV guide URL**, then OK.
   - Playlist and guide URLs are remembered between sessions.
3. Browse **Live TV / Movies / Series** in the left sidebar, filter by category, or search.
4. **Click any channel card** to play it in the bottom video panel.
5. ⭐ Star channels to pin them under **Favorites**.
6. Open the **🗓 EPG Guide** page for the 6-hour programme timeline.
7. **⚙ Settings** page: default volume, mute, recent history.

### Where do I get a playlist?

Use any M3U/M3U8 playlist from your IPTV provider, e.g.:

```
https://provider.example/get.php?username=USER&password=PASS&type=m3u_plus
```

and an XMLTV EPG URL like:

```
https://provider.example/xmltv.php?username=USER&password=PASS
```

## Project layout

```
iptv-player/
├── main.py               # entry point
├── run.sh                # Linux helper script (handles Wayland fallback)
├── requirements.txt
├── README.md
├── app/
│   ├── config.py         # QSettings wrapper (volume, last playlist, geometry…)
│   ├── models.py         # Channel / EPGProgram dataclasses
│   ├── playlist.py       # M3U parser (EXTINF attrs), file+URL loading, filters
│   ├── epg.py            # XMLTV parser (xmltodict), now/next + guide queries
│   ├── player.py         # self-contained engine: PyAV (FFmpeg) decode in a
│   │                       # QThread, QAudioSink audio, frame_ready(QImage) video
│   └── favorites.py      # JSON favorites store
└── ui/
    ├── theme.py          # dark QSS theme, accent #8b5cf6
    ├── main_window.py    # QMainWindow: sidebar, grids, EPG page, player bar
    ├── widgets.py        # ChannelCard, ChannelGrid, async LogoLabel, EPG timeline
    └── dialogs.py        # Add-playlist + Settings dialogs
```

## Troubleshooting

- **Black video / nothing plays** → check the stream URL works in a browser or
  another player; some providers expire tokens hourly or geo-block streams.
- HTTP user-agent and referrer settings in `#EXTVLCOPT` playlist lines are
  passed to the stream decoder. Streams that require other client-specific
  options may still need a provider-compatible player.
- **`import av` fails** → run `pip install "av>=11"` and retry. PyAV wheels
  bundle FFmpeg, so no system packages are needed.
- **No audio but video works** → the stream may have no audio track, or the
  audio codec isn't in the bundled FFmpeg build. Try another channel to compare.
- **Choppy playback** → late video frames are dropped automatically to stay in
  sync; persistent choppiness usually means a slow network or an overloaded
  provider server.
- **Playlist fails to load** → check the URL in a browser; some providers expire tokens hourly.
- **No EPG data** → make sure the XMLTV URL matches your provider and channel `tvg-id`s line up.
- **Logos missing** → the app shows a 📺 placeholder when a logo URL is empty or unreachable.

## License

MIT — do what you like, just don't blame us when the big match buffers. 😉
