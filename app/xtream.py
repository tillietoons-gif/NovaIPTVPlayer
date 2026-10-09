"""Xtream Codes API client (Smarters-Pro style providers).

Speaks the ``player_api.php`` protocol used by Xtream Codes / Xtream UI
panels: login, categories, stream listings, VOD/series details, short EPG,
and stream-URL builders. All calls use :mod:`requests` with a timeout and
raise :class:`XtreamError` (or the :class:`XtreamAuthError` subclass) with a
human-readable message instead of leaking transport exceptions. Malformed
or partially missing JSON is tolerated everywhere -- providers vary wildly
in what they return.

No network calls happen at import time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

_TIMEOUT_S = 20
_USER_AGENT = "NovaIPTV/1.0"


class XtreamError(Exception):
    """Any failure talking to an Xtream Codes panel."""


class XtreamAuthError(XtreamError):
    """Credentials were rejected (user_info.auth != 1)."""


def _as_list(payload: Any) -> list[Any]:
    """Providers sometimes return {} instead of [] -- normalize both."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload] if payload else []
    return []


def _as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def _ts_to_dt(value: Any) -> datetime | None:
    """Unix timestamp (str or int) -> aware datetime, or None."""
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def normalize_server(server: str) -> str:
    """Normalize a panel URL: force http(s) scheme, strip trailing slash."""
    server = (server or "").strip().rstrip("/")
    if not server:
        raise XtreamError("Server URL is empty.")
    if not server.lower().startswith(("http://", "https://")):
        server = "http://" + server
    return server


class XtreamClient:
    """Thin client for one Xtream Codes provider account."""

    def __init__(self, server: str, username: str, password: str) -> None:
        self.server = normalize_server(server)
        self.username = (username or "").strip()
        self.password = password or ""
        self.user_info: dict[str, Any] = {}
        self.server_info: dict[str, Any] = {}

    # -- internals ---------------------------------------------------------
    def _api(self, params: dict[str, Any]) -> Any:
        """GET player_api.php with the given params; return parsed JSON."""
        try:
            resp = requests.get(
                f"{self.server}/player_api.php",
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT_S,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise XtreamError(f"Network error: {exc}") from exc
        try:
            return resp.json()
        except ValueError as exc:
            raise XtreamError(
                "Server did not return valid JSON. Check the server URL "
                "and that it is an Xtream Codes panel."
            ) from exc

    def _authed(self, params: dict[str, Any]) -> Any:
        params = dict(params)
        params.setdefault("username", self.username)
        params.setdefault("password", self.password)
        return self._api(params)

    # -- login / account ---------------------------------------------------
    def login(self) -> dict[str, Any]:
        """Authenticate and cache user_info/server_info.

        Raises XtreamAuthError when the panel rejects the credentials.
        Returns {"user_info": ..., "server_info": ...}.
        """
        data = _as_dict(self._api({
            "username": self.username,
            "password": self.password,
        }))
        user_info = _as_dict(data.get("user_info"))
        if str(user_info.get("auth")) != "1":
            raise XtreamAuthError(
                "Invalid username or password (panel rejected the login).")
        self.user_info = user_info
        self.server_info = _as_dict(data.get("server_info"))
        return {"user_info": self.user_info, "server_info": self.server_info}

    def account_expiry(self) -> datetime | None:
        """Account expiry as aware datetime, or None if unknown/lifetime."""
        return _ts_to_dt(self.user_info.get("exp_date"))

    def is_active(self) -> bool:
        return str(self.user_info.get("status", "")).lower() == "active"

    # -- categories --------------------------------------------------------
    def _categories(self, action: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for item in _as_list(self._authed({"action": action})):
            item = _as_dict(item)
            cid = str(item.get("category_id", ""))
            name = str(item.get("category_name", "")).strip()
            if cid and name:
                out.append((cid, name))
        return out

    def live_categories(self) -> list[tuple[str, str]]:
        return self._categories("get_live_categories")

    def vod_categories(self) -> list[tuple[str, str]]:
        return self._categories("get_vod_categories")

    def series_categories(self) -> list[tuple[str, str]]:
        return self._categories("get_series_categories")

    # -- stream listings ---------------------------------------------------
    def _streams(self, action: str, category_id: str | None,
                 want_epg: bool = False) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"action": action}
        if category_id:
            params["category_id"] = category_id
        out: list[dict[str, Any]] = []
        for item in _as_list(self._authed(params)):
            item = _as_dict(item)
            sid = str(item.get("stream_id", "") or item.get("series_id", ""))
            if not sid:
                continue
            entry: dict[str, Any] = {
                "id": sid,
                "name": str(item.get("name", "")).strip() or f"Stream {sid}",
                "icon": str(item.get("stream_icon", "") or item.get("cover", "") or ""),
                "category_id": str(item.get("category_id", "") or ""),
                "_raw": item,
            }
            if want_epg:
                entry["epg_id"] = str(item.get("epg_channel_id", "") or "")
            out.append(entry)
        return out

    def live_streams(
            self, category_id: str | None = None) -> list[dict[str, Any]]:
        return self._streams("get_live_streams", category_id, want_epg=True)

    def vod_streams(
            self, category_id: str | None = None) -> list[dict[str, Any]]:
        return self._streams("get_vod_streams", category_id)

    def series_list(
            self, category_id: str | None = None) -> list[dict[str, Any]]:
        return self._streams("get_series", category_id)

    # -- details -----------------------------------------------------------
    def vod_info(self, vod_id: str | int) -> dict[str, Any]:
        """Normalized movie metadata (info.movie_data + stream fields)."""
        data = _as_dict(self._authed(
            {"action": "get_vod_info", "vod_id": vod_id}))
        info = _as_dict(data.get("info"))
        movie = _as_dict(data.get("movie_data")) or info
        return {
            "id": str(vod_id),
            "name": str(movie.get("name", "") or info.get("name", "")),
            "cover": str(movie.get("stream_icon", "")
                          or info.get("movie_image", "") or ""),
            "rating": str(movie.get("rating", "") or ""),
            "year": str(movie.get("releasedate", "")
                        or movie.get("releaseDate", "") or ""),
            "genre": str(movie.get("genre", "") or ""),
            "plot": str(movie.get("plot", "") or ""),
            "cast": str(movie.get("cast", "") or ""),
            "director": str(movie.get("director", "") or ""),
            "duration": str(movie.get("duration", "") or ""),
            "youtube_trailer": str(movie.get("youtube_trailer", "") or ""),
            "container_extension": str(
                _as_dict(data.get("movie_data")).get("container_extension", "")
                or "mp4"),
            "_raw": data,
        }

    def series_info(self, series_id: str | int) -> dict[str, Any]:
        """Normalized series metadata with seasons -> episode lists.

        Each episode: id, episode_num, title, plot, duration, icon,
        container_extension.
        """
        data = _as_dict(self._authed(
            {"action": "get_series_info", "series_id": series_id}))
        info = _as_dict(data.get("info"))
        seasons: dict[str, list[dict[str, Any]]] = {}
        episodes = _as_dict(data.get("episodes"))
        for season_num, eps in episodes.items():
            season_eps: list[dict[str, Any]] = []
            for ep in _as_list(eps):
                ep = _as_dict(ep)
                eid = str(ep.get("id", ""))
                if not eid:
                    continue
                season_eps.append({
                    "id": eid,
                    "episode_num": str(ep.get("episode_num", "") or ""),
                    "title": str(ep.get("title", "") or ""),
                    "plot": str(ep.get("plot", "") or ""),
                    "duration": str(ep.get("duration", "") or ""),
                    "icon": str(ep.get("info", {}).get("movie_image", "")
                                or ""),
                    "container_extension": str(
                        ep.get("container_extension", "") or "mp4"),
                })
            season_eps.sort(
                key=lambda e: int(e["episode_num"])
                if e["episode_num"].isdigit() else 0)
            seasons[str(season_num)] = season_eps
        return {
            "id": str(series_id),
            "name": str(info.get("name", "")),
            "cover": str(info.get("cover", "") or ""),
            "genre": str(info.get("genre", "") or ""),
            "plot": str(info.get("plot", "") or ""),
            "cast": str(info.get("cast", "") or ""),
            "director": str(info.get("director", "") or ""),
            "rating": str(info.get("rating", "") or ""),
            "youtube_trailer": str(info.get("youtube_trailer", "") or ""),
            "seasons": seasons,
            "_raw": data,
        }

    # -- EPG ---------------------------------------------------------------
    def xmltv_url(self) -> str:
        """Full XMLTV guide URL for this account (works with EPGManager)."""
        return (f"{self.server}/xmltv.php?username={self.username}"
                f"&password={self.password}")

    # -- stream URL builders ------------------------------------------------
    def live_url(self, stream_id: str | int) -> str:
        return (f"{self.server}/live/{self.username}/{self.password}"
                f"/{stream_id}.m3u8")

    def vod_url(self, vod_id: str | int, ext: str | None = None) -> str:
        ext = (ext or "mp4").lstrip(".") or "mp4"
        return (f"{self.server}/movie/{self.username}/{self.password}"
                f"/{vod_id}.{ext}")

    def episode_url(self, episode_id: str | int,
                    ext: str | None = None) -> str:
        ext = (ext or "mp4").lstrip(".") or "mp4"
        return (f"{self.server}/series/{self.username}/{self.password}"
                f"/{episode_id}.{ext}")
