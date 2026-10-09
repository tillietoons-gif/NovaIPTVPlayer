"""XMLTV EPG parsing, fetching and programme lookup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import xmltodict

from app.models import EPGProgram

_EPG_TIME_FORMATS = ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M%S")


def _parse_time(value: str) -> datetime:
    value = value.strip()
    for fmt in _EPG_TIME_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unparseable XMLTV time: {value!r}")


def _text(node) -> str:
    if node is None:
        return ""
    if isinstance(node, dict):
        return str(node.get("#text", "") or "")
    return str(node)


class EPGManager:
    """Loads an XMLTV guide and answers now/next queries per channel."""

    def __init__(self) -> None:
        # channel_id -> sorted list[EPGProgram]
        self._programs: dict[str, list[EPGProgram]] = {}
        self._channels: dict[str, str] = {}  # id -> display name
        self.source: str = ""

    # -- loading ----------------------------------------------------------
    def load(self, source: str, timeout: int = 60) -> int:
        """Load XMLTV from a file path or URL. Returns programme count."""
        source = source.strip()
        if not source:
            raise ValueError("EPG source is empty.")
        if urlparse(source).scheme in ("http", "https", "ftp"):
            resp = requests.get(
                source, timeout=timeout, headers={"User-Agent": "NovaIPTV/1.0"}
            )
            resp.raise_for_status()
            data = resp.content
        else:
            data = Path(source).expanduser().read_bytes()

        doc = xmltodict.parse(data, force_list=("channel", "programme"))
        tv = doc.get("tv") or {}

        channels: dict[str, str] = {}
        for ch in tv.get("channel", []) or []:
            cid = ch.get("@id", "")
            names = ch.get("display-name")
            if isinstance(names, list):
                name = _text(names[0])
            else:
                name = _text(names)
            if cid:
                channels[cid] = name or cid

        programs: dict[str, list[EPGProgram]] = {}
        count = 0
        for p in tv.get("programme", []) or []:
            try:
                cid = p.get("@channel", "")
                prog = EPGProgram(
                    channel_id=cid,
                    title=_text(p.get("title")) or "Unknown",
                    start=_parse_time(p.get("@start", "")),
                    stop=_parse_time(p.get("@stop", "")),
                    desc=_text(p.get("desc")),
                )
            except (ValueError, TypeError):
                continue
            programs.setdefault(cid, []).append(prog)
            count += 1

        for plist in programs.values():
            plist.sort(key=lambda pr: pr.start)

        self._channels = channels
        self._programs = programs
        self.source = source
        return count

    # -- queries ----------------------------------------------------------
    @property
    def loaded(self) -> bool:
        return bool(self._programs)

    def channel_ids(self) -> list[str]:
        return sorted(self._programs.keys())

    def _match_ids(self, channel_tvg_id: str, channel_name: str) -> list[str]:
        """Find programme lists whose XMLTV id matches the channel's
        tvg-id, falling back to a case-insensitive name match."""
        if channel_tvg_id and channel_tvg_id in self._programs:
            return [channel_tvg_id]
        lname = channel_name.lower()
        return [
            cid
            for cid in self._programs
            if cid.lower() == lname
            or self._channels.get(cid, "").lower() == lname
        ]

    def programs_for(self, channel_tvg_id: str, channel_name: str = "") -> list[EPGProgram]:
        ids = self._match_ids(channel_tvg_id, channel_name)
        out: list[EPGProgram] = []
        for cid in ids:
            out.extend(self._programs.get(cid, []))
        out.sort(key=lambda pr: pr.start)
        return out

    def now_and_next(
        self,
        channel_tvg_id: str,
        channel_name: str = "",
        now: datetime | None = None,
    ) -> tuple[EPGProgram | None, EPGProgram | None]:
        """Return (current, next) programme airing around *now*."""
        now = now or datetime.now(timezone.utc)
        progs = self.programs_for(channel_tvg_id, channel_name)
        current: EPGProgram | None = None
        nxt: EPGProgram | None = None
        for i, pr in enumerate(progs):
            if pr.start <= now < pr.stop:
                current = pr
                nxt = progs[i + 1] if i + 1 < len(progs) else None
                break
            if pr.start > now:
                nxt = pr
                break
        return current, nxt

    def guide_window(
        self,
        channel_tvg_id: str,
        channel_name: str = "",
        start: datetime | None = None,
        hours: int = 6,
    ) -> list[EPGProgram]:
        """Programmes overlapping [start, start+hours)."""
        from datetime import timedelta

        start = start or datetime.now(timezone.utc)
        end = start + timedelta(hours=hours)
        return [
            pr
            for pr in self.programs_for(channel_tvg_id, channel_name)
            if pr.stop > start and pr.start < end
        ]
