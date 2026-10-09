#!/usr/bin/env bash
# Nova IPTV Player - Linux launcher.
# The player engine is self-contained (PyAV bundles FFmpeg), so no
# system media packages are required -- just Python and pip deps.
set -e
cd "$(dirname "$0")"

if ! python3 -c "import av" 2>/dev/null; then
  echo "WARNING: PyAV is not installed. Install dependencies first:"
  echo "  pip install -r requirements.txt"
fi

exec python3 main.py "$@"
