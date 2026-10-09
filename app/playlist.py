"""M3U / M3U8 playlist parsing and loading.

Supports the common Xtream-style EXTINF attributes:
    #EXTINF:-1 tvg-id="..." tvg-logo="..." group-title="...",Channel Name
    http://example.com/stream

Both local files and remote URLs are supported. Channels are classified
into live / movie / series using group-title heuristics.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.models import Channel

_EXTINF_RE = re.compile(r'^#EXTINF:(?P<duration>-?\d+)\s*(?P<attrs>.*?),(?P<name>.*)$')
_ATTR_RE = re.compile(r'([\w\-]+)="([^"]*)"')

_MOVIE_HINTS = ("movie", "movies", "vod", "films", "cinema")
_SERIES_HINTS = ("series", "show", "shows", "tv shows", "episodes")


def _classify(group: str, name: str) -> str:
    g = group.lower()
    n = name.lower()
    if any(h in g or h in n for h in _SERIES_HINTS):
        # "tv shows" style groups are series; plain "tv" stays live
        if "series" in g or "series" in n or "show" in g:
            return "series"
    if any(h in g or h in n for h in _MOVIE_HINTS):
        return "movie"
    return "live"


def parse_m3u(text: str) -> list[Channel]:
    """Parse raw M3U text into Channel objects."""
    channels: list[Channel] = []
    pending_name = ""
    pending_attrs: dict[str, str] = {}
    pending_headers: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            m = _EXTINF_RE.match(line)
            if m:
                pending_name = m.group("name").strip()
                pending_attrs = dict(_ATTR_RE.findall(m.group("attrs")))
                pending_headers = {}
            else:
                # Malformed EXTINF: take everything after the first comma.
                pending_name = line.split(",", 1)[-1].strip()
                pending_attrs = {}
                pending_headers = {}
        elif line.upper().startswith("#EXTVLCOPT:"):
            option = line[len("#EXTVLCOPT:"):]
            key, separator, value = option.partition("=")
            header = {
                "http-user-agent": "User-Agent",
                "http-referrer": "Referer",
                "http-referer": "Referer",
            }.get(key.strip().lower())
            if separator and header:
                pending_headers[header] = value.strip()
        elif line.startswith("#"):
            continue  # other directives (EXTM3U, EXT-X-*, ...) are ignored
        else:
            # This line is the stream URL for the pending EXTINF entry.
            url = line
            if not url or not _looks_like_stream_url(url):
                pending_name = ""
                pending_attrs = {}
                continue
            if pending_name or url:
                group = (
                    pending_attrs.get("group-title")
                    or pending_attrs.get("group_title")
                    or ""
                )
                name = pending_name.strip() or url.rsplit("/", 1)[-1]
                if not name:
                    pending_name = ""
                    pending_attrs = {}
                    continue
                channels.append(
                    Channel(
                        name=name,
                        url=url,
                        tvg_id=pending_attrs.get("tvg-id", ""),
                        logo=pending_attrs.get("tvg-logo", ""),
                        group=group,
                        kind=_classify(group, name),
                        stream_headers=pending_headers.copy(),
                        catchup=bool(pending_attrs.get("catchup") or pending_attrs.get("catchup-type")),
                        catchup_days=int(pending_attrs.get("catchup-days", 0) or 0),
                        catchup_source=pending_attrs.get("catchup-source", ""),
                    )
                )
            pending_name = ""
            pending_attrs = {}
            pending_headers = {}
    return channels


def _looks_like_url(source: str) -> bool:
    try:
        return urlparse(source).scheme in ("http", "https", "ftp")
    except Exception:
        return False


def _looks_like_stream_url(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    try:
        scheme = urlparse(value).scheme.lower()
    except Exception:
        return False
    if scheme in {"http", "https", "ftp", "rtmp", "rtmps", "rtsp", "rtp", "udp", "tcp", "mms", "file"}:
        return True
    return False


def load_playlist(source: str, timeout: int = 30) -> list[Channel]:
    """Load a playlist from a local file path or a remote URL."""
    source = source.strip()
    if not source:
        raise ValueError("Playlist source is empty.")
    if _looks_like_url(source):
        resp = requests.get(
            source,
            timeout=timeout,
            headers={"User-Agent": "NovaIPTV/1.0"},
            allow_redirects=True,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        text = resp.text
    else:
        path = Path(source).expanduser()
        if not path.exists() or not path.is_file():
            raise ValueError(f"Playlist file does not exist: {source}")
        text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError("Playlist source is empty or unreadable.")
    return parse_m3u(text)


def categories(channels: list[Channel], kind: str | None = None) -> list[str]:
    """Sorted unique group names, optionally filtered by channel kind."""
    groups = {
        c.display_group
        for c in channels
        if kind is None or c.kind == kind
    }
    return sorted(groups, key=str.lower)


def filter_channels(
    channels: list[Channel],
    query: str = "",
    category: str = "",
    kind: str | None = None,
) -> list[Channel]:
    """Apply search / category / kind filters."""
    q = query.strip().lower()
    out = []
    for c in channels:
        if kind is not None and c.kind != kind:
            continue
        if category and c.display_group != category:
            continue
        if q and q not in c.name.lower():
            continue
        out.append(c)
    return out
