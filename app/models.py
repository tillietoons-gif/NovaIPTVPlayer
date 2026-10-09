"""Data models shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Channel:
    """A single entry parsed from an M3U/M3U8 playlist."""

    name: str
    url: str
    id: str = ""
    tvg_id: str = ""
    logo: str = ""
    group: str = ""
    kind: str = "live"  # one of: live | movie | series
    stream_headers: dict[str, str] = field(default_factory=dict)
    # Xtream Codes metadata (optional; empty for plain M3U entries).
    provider_id: str = ""
    stream_id: str = ""        # xtream numeric id (live/vod) or episode id
    series_id: str = ""        # xtream series id (episodes point back here)
    season: str = ""
    episode_num: str = ""
    rating: str = ""
    year: str = ""
    plot: str = ""
    cast: str = ""
    director: str = ""
    genre: str = ""
    duration: str = ""
    container_ext: str = ""
    catchup: bool = False
    catchup_days: int = 0
    catchup_source: str = ""

    @property
    def display_group(self) -> str:
        return self.group or "Uncategorized"

    def build_catchup_url(self, start_or_client=None, duration_or_program=60, duration_minutes: int = 60) -> str | None:
        """Construct catchup archive playback URL for M3U and Xtream channels.

        Can be called as:
          channel.build_catchup_url(start_dt, duration_minutes=60)
          channel.build_catchup_url(xtream_client, epg_program)
        """
        if isinstance(start_or_client, datetime):
            start_dt = start_or_client
            dur_mins = duration_minutes if duration_minutes != 60 else (
                duration_or_program if isinstance(duration_or_program, int) else 60
            )

            start_utc = int(start_dt.timestamp())
            now_utc = int(datetime.now().timestamp())
            offset = max(0, now_utc - start_utc)
            dur_secs = max(1, dur_mins * 60)

            src = self.catchup_source or ""
            if src:
                res = src.replace("${start}", str(start_utc))
                res = res.replace("${timestamp}", str(now_utc))
                res = res.replace("${offset}", str(offset))
                res = res.replace("${duration}", str(dur_secs))
                res = res.replace("${lutc}", str(now_utc))
                res = res.replace("${utc}", str(start_utc))
                res = res.replace("${utcend}", str(start_utc + dur_secs))
                res = res.replace("${Y}", start_dt.strftime("%Y"))
                res = res.replace("${m}", start_dt.strftime("%m"))
                res = res.replace("${d}", start_dt.strftime("%d"))
                res = res.replace("${H}", start_dt.strftime("%H"))
                res = res.replace("${M}", start_dt.strftime("%M"))
                res = res.replace("${S}", start_dt.strftime("%S"))
                if src.startswith("?") or src.startswith("&"):
                    sep = "&" if "?" in self.url else "?"
                    clean_res = res.lstrip("?").lstrip("&")
                    return f"{self.url}{sep}{clean_res}"
                return res

            mode = str(self.catchup or "").lower()
            if mode in ("flussonic", "shift"):
                base = self.url.rstrip("/")
                if "tracks-v1a1/mono.m3u8" in base:
                    return base.replace("tracks-v1a1/mono.m3u8", f"timeshift_rel-{offset}.m3u8")
                return f"{base}/timeshift_rel-{offset}.m3u8"
            else:
                sep = "&" if "?" in self.url else "?"
                return f"{self.url}{sep}utc={start_utc}&lutc={now_utc}"

        # Xtream client + EPGProgram calling pattern
        client = start_or_client
        program = duration_or_program
        if client is not None and getattr(self, "stream_id", None) and hasattr(program, "start"):
            dur_mins = max(1, int((program.stop - program.start).total_seconds() // 60))
            return client.timeshift_url(self.stream_id, program.start, dur_mins)

        return None


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


# -- Xtream Codes -> Channel converters ---------------------------------------
# These keep the rest of the app (grids, favorites, EPG matching, player)
# working unchanged: an Xtream provider simply materializes Channels.

def _epg_id_of(stream: dict) -> str:
    return str(stream.get("epg_id", "") or "")


def xtream_live_to_channels(client, streams: list[dict],
                            provider_id: str = "") -> list[Channel]:
    """Convert get_live_streams() entries to live Channels.

    The Xtream epg_channel_id becomes tvg_id so XMLTV guide matching keeps
    working exactly like M3U tvg-id entries.
    """
    channels: list[Channel] = []
    for s in streams:
        tv_arch = int(s.get("tv_archive", 0) or 0)
        arch_dur = int(s.get("tv_archive_duration", 0) or 0)
        channels.append(Channel(
            name=s.get("name", "") or f"Stream {s.get('id', '')}",
            url=client.live_url(s["id"]),
            tvg_id=_epg_id_of(s),
            logo=s.get("icon", "") or "",
            group="",  # UI can resolve category_id -> name via client
            kind="live",
            provider_id=provider_id,
            stream_id=str(s.get("id", "")),
            catchup=bool(tv_arch),
            catchup_days=arch_dur or (3 if tv_arch else 0),
        ))
    return channels


def xtream_vod_to_channels(client, streams: list[dict],
                           provider_id: str = "") -> list[Channel]:
    """Convert get_vod_streams() entries to movie Channels (lightweight).

    Callers can enrich individual entries later with vod_info().
    """
    channels: list[Channel] = []
    for s in streams:
        channels.append(Channel(
            name=s.get("name", "") or f"Movie {s.get('id', '')}",
            url=client.vod_url(s["id"]),
            logo=s.get("icon", "") or "",
            kind="movie",
            provider_id=provider_id,
            stream_id=str(s.get("id", "")),
        ))
    return channels


def xtream_vod_detail_to_channel(client, vod_id: str | int,
                                 info: dict,
                                 provider_id: str = "") -> Channel:
    """Build a fully-detailed movie Channel from vod_info() output."""
    ext = str(info.get("container_extension", "") or "mp4")
    return Channel(
        name=info.get("name", "") or f"Movie {vod_id}",
        url=client.vod_url(vod_id, ext),
        logo=info.get("cover", "") or "",
        kind="movie",
        provider_id=provider_id,
        stream_id=str(vod_id),
        rating=info.get("rating", "") or "",
        year=info.get("year", "") or "",
        plot=info.get("plot", "") or "",
        cast=info.get("cast", "") or "",
        director=info.get("director", "") or "",
        genre=info.get("genre", "") or "",
        duration=info.get("duration", "") or "",
        container_ext=ext,
    )


def xtream_series_to_channels(client, series_entries: list[dict],
                              provider_id: str = "") -> list[Channel]:
    """Convert get_series() entries to series *container* Channels.

    One Channel per series (kind="series"); expand episodes on demand with
    xtream_episodes_to_channels().
    """
    channels: list[Channel] = []
    for s in series_entries:
        sid = str(s.get("id", ""))
        channels.append(Channel(
            name=s.get("name", "") or f"Series {sid}",
            url=f"xtream://series/{sid}" if sid else "",
            logo=s.get("icon", "") or "",
            kind="series",
            provider_id=provider_id,
            series_id=sid,
        ))
    return channels


def xtream_episodes_to_channels(client, series_id: str | int,
                                series_name: str,
                                episodes_by_season: dict,
                                provider_id: str = "") -> list[Channel]:
    """Flatten series_info()['seasons'] into playable episode Channels.

    Episode names look like "S1 E2 - Title" and group under the series name.
    """
    channels: list[Channel] = []
    for season_num in sorted(episodes_by_season,
                             key=lambda k: int(k) if str(k).isdigit() else 0):
        for ep in episodes_by_season[season_num] or []:
            ep_num = str(ep.get("episode_num", "") or "")
            title = str(ep.get("title", "") or "")
            label = f"S{season_num} E{ep_num}" + (f" - {title}" if title else "")
            channels.append(Channel(
                name=label,
                url=client.episode_url(ep["id"],
                                       ep.get("container_extension")),
                logo=ep.get("icon", "") or "",
                group=str(series_name or ""),
                kind="series",
                provider_id=provider_id,
                stream_id=str(ep.get("id", "")),
                series_id=str(series_id),
                season=str(season_num),
                episode_num=ep_num,
                plot=ep.get("plot", "") or "",
                duration=ep.get("duration", "") or "",
                container_ext=str(ep.get("container_extension", "")
                                  or "mp4"),
            ))
    return channels
