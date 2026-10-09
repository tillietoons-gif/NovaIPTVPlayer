"""Data models shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Channel:
    """A single entry parsed from an M3U/M3U8 playlist."""

    name: str
    url: str
    tvg_id: str = ""
    logo: str = ""
    group: str = ""
    kind: str = "live"  # one of: live | movie | series

    @property
    def display_group(self) -> str:
        return self.group or "Uncategorized"


@dataclass
class EPGProgram:
    """A single programme from an XMLTV guide."""

    channel_id: str
    title: str
    start: datetime
    stop: datetime
    desc: str = ""


@dataclass
class HistoryEntry:
    channel_url: str
    channel_name: str
    played_at: datetime = field(default_factory=datetime.now)
