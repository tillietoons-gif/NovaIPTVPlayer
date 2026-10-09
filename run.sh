#!/usr/bin/env bash
# Nova IPTV Player - Linux launcher
# Falls back to X11 (xcb) on Wayland for reliable VLC video embedding.
set -e
cd "$(dirname "$0")"

if [ -z "$QT_QPA_PLATFORM" ] && [ "$XDG_SESSION_TYPE" = "wayland" ]; then
  echo "Wayland detected -> using QT_QPA_PLATFORM=xcb for VLC embedding"
  export QT_QPA_PLATFORM=xcb
fi

if ! python3 -c "import vlc" 2>/dev/null; then
  echo "WARNING: python-vlc cannot find libvlc. Install VLC first:"
  echo "  Ubuntu/Debian: sudo apt install vlc"
  echo "  Fedora:        sudo dnf install vlc"
  echo "  Arch:          sudo pacman -S vlc"
fi

exec python3 main.py "$@"
