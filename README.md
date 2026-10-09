# ⚡ Nova IPTV Player

An advanced IPTV player for **Windows and Linux** with a modern dark UI, built with
**PySide6 (Qt6)** and **python-vlc** (VLC backend — best for HLS / DASH / RTSP
streams).

Features:

- 📡 Load M3U/M3U8 playlists from **file or URL** (Xtream-style `#EXTINF` with `tvg-id`, `tvg-logo`, `group-title`)
- 🎬 Automatic **Live TV / Movies / Series** classification + category filter + instant search
- 🗓 **XMLTV EPG** support: now/next on every card, 6-hour timeline guide
- ⭐ **Favorites** persisted to JSON, toggle with the star on any card
- 🕘 **Recent history** with double-click replay
- 🔊 Volume slider, mute, pause/resume, stop, fullscreen video
- 🌙 Dark glassy theme with `#00d4ff` accent, async logo loading

## Requirements

| # | Requirement | Windows | Linux |
|---|-------------|---------|-------|
| 1 | OS 64-bit | Windows 10/11 | Ubuntu 22.04+ / Fedora / Arch (any modern distro) |
| 2 | Python 3.10+ 64-bit | Must match VLC bitness | From distro or python.org |
| 3 | VLC 64-bit | Install from [videolan.org](https://www.videolan.org/vlc/) | `sudo apt install vlc` (Debian/Ubuntu) or `sudo dnf install vlc` (Fedora) |
| 4 | libvlc discoverable | python-vlc finds it via VLC install folder | python-vlc finds it via system libvlc |

> ⚠️ If `import vlc` fails on Windows, 99% of the time it's a **32-bit vs 64-bit mismatch**
> between Python and VLC. Install 64-bit everything. On Linux, make sure the
> `vlc` package is installed, not just `libvlc`.

## Setup (Windows)

```powershell
# 1. Install VLC 64-bit from https://www.videolan.org/vlc/

# 2. Install dependencies
cd iptv-player
pip install -r requirements.txt

# 3. Run
python main.py
```

## Setup (Linux)

```bash
# 1. Install VLC + Python dev tools (Debian/Ubuntu example)
sudo apt update
sudo apt install vlc python3-pip

# Fedora:
# sudo dnf install vlc python3-pip
# Arch:
# sudo pacman -S vlc

# 2. Install dependencies
cd iptv-player
pip install -r requirements.txt

# 3. Run
python3 main.py
# or use the helper script:
# ./run.sh
```

> 🐧 **Wayland note:** VLC video embedding works best under XWayland. If you get
> a black video on Wayland, run with `QT_QPA_PLATFORM=xcb python3 main.py`
> to force X11 mode.

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
│   ├── player.py         # python-vlc controller (set_hwnd on Windows, set_xwindow on Linux)
│   └── favorites.py      # JSON favorites store
└── ui/
    ├── theme.py          # dark QSS theme, accent #00d4ff
    ├── main_window.py    # QMainWindow: sidebar, grids, EPG page, player bar
    ├── widgets.py        # ChannelCard, ChannelGrid, async LogoLabel, EPG timeline
    └── dialogs.py        # Add-playlist + Settings dialogs
```

## Troubleshooting

- **Black video / nothing plays (Windows)** → install VLC 64-bit, restart the app. Check the stream URL works in VLC itself.
- **Black video (Linux/Wayland)** → run with `QT_QPA_PLATFORM=xcb python3 main.py`.
- **`import vlc` fails (Linux)** → `sudo apt install vlc` and retry; python-vlc needs system libvlc.
- **Playlist fails to load** → check the URL in a browser; some providers expire tokens hourly.
- **No EPG data** → make sure the XMLTV URL matches your provider and channel `tvg-id`s line up.
- **Logos missing** → the app shows a 📺 placeholder when a logo URL is empty or unreachable.

## License

MIT — do what you like, just don't blame us when the big match buffers. 😉
