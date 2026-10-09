"""Multi-provider profiles (Smarters-Pro style).

A profile describes one provider: either an Xtream Codes panel login or a
plain M3U playlist URL. Profiles are stored as JSON under the platform app
data directory; the active profile id is persisted alongside. Passwords are
only ever written to that local JSON file -- never logged.

No network calls happen at import time.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QStandardPaths

if TYPE_CHECKING:  # avoid a hard import cycle; only used for typing
    from app.config import AppConfig


def _default_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    return Path(base or ".") / "profiles.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProviderProfile:
    """One provider: an Xtream Codes login or an M3U playlist."""

    id: str = ""                      # uuid4 hex, assigned by ProfileStore
    name: str = ""
    kind: str = "m3u"                 # "xtream" | "m3u"
    server: str = ""                  # xtream: panel base URL
    username: str = ""                # xtream only
    password: str = ""                # xtream only (local JSON only)
    playlist_url: str = ""            # m3u: local path or remote URL
    epg_url: str = ""                 # optional XMLTV override
    created_at: str = ""              # ISO timestamp, assigned by store

    def is_xtream(self) -> bool:
        return self.kind == "xtream"

    def redacted(self) -> str:
        """One-line summary that never includes the password."""
        if self.is_xtream():
            who = f"{self.username}@{self.server}" if self.username else self.server
        else:
            who = self.playlist_url
        return f"{self.name} [{self.kind}] {who}"


class ProfileStore:
    """JSON-backed store of provider profiles + the active profile id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _default_path()
        self._profiles: list[ProviderProfile] = []
        self._active_id: str = ""
        self._load()

    # -- persistence ------------------------------------------------------
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for raw in data.get("profiles", []):
            if not isinstance(raw, dict):
                continue
            try:
                self._profiles.append(ProviderProfile(**{
                    k: raw.get(k, "") for k in ProviderProfile.__dataclass_fields__
                }))
            except TypeError:
                continue  # skip entries from a newer/older schema
        active = str(data.get("active_id", ""))
        if any(p.id == active for p in self._profiles):
            self._active_id = active

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "active_id": self._active_id,
                "profiles": [asdict(p) for p in self._profiles],
            }
            self.path.write_text(
                json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass  # profile persistence is best-effort; never crash the app

    # -- CRUD -------------------------------------------------------------
    def all(self) -> list[ProviderProfile]:
        return list(self._profiles)

    def get(self, profile_id: str) -> ProviderProfile | None:
        for p in self._profiles:
            if p.id == profile_id:
                return p
        return None

    def add(self, profile: ProviderProfile) -> ProviderProfile:
        if not profile.id:
            profile.id = uuid.uuid4().hex
        if not profile.created_at:
            profile.created_at = _utcnow_iso()
        if self.get(profile.id) is not None:
            raise ValueError(f"Duplicate profile id: {profile.id}")
        self._profiles.append(profile)
        if not self._active_id:
            self._active_id = profile.id
        self._save()
        return profile

    def update(self, profile: ProviderProfile) -> None:
        for i, existing in enumerate(self._profiles):
            if existing.id == profile.id:
                self._profiles[i] = profile
                self._save()
                return
        raise KeyError(f"Unknown profile id: {profile.id}")

    def remove(self, profile_id: str) -> bool:
        before = len(self._profiles)
        self._profiles = [p for p in self._profiles if p.id != profile_id]
        if self._active_id == profile_id:
            self._active_id = self._profiles[0].id if self._profiles else ""
        removed = len(self._profiles) < before
        if removed:
            self._save()
        return removed

    # -- active profile ---------------------------------------------------
    @property
    def active_id(self) -> str:
        return self._active_id

    def active(self) -> ProviderProfile | None:
        return self.get(self._active_id)

    def set_active(self, profile_id: str) -> None:
        if self.get(profile_id) is None:
            raise KeyError(f"Unknown profile id: {profile_id}")
        self._active_id = profile_id
        self._save()

    def exists(self) -> bool:
        """True when the store file has been created (used by migration)."""
        return self.path.exists()


def migrate_legacy(config: "AppConfig") -> bool:
    """Create an m3u profile from the legacy single-playlist settings.

    Runs only when no profiles.json exists yet and the legacy
    ``playlist_source`` is set. Returns True when a profile was created.
    The legacy config values are left untouched (fallback still works).
    """
    store = ProfileStore()
    if store.exists():
        return False
    source = (config.playlist_source or "").strip()
    if not source:
        return False
    store.add(ProviderProfile(
        name="My Playlist",
        kind="m3u",
        playlist_url=source,
        epg_url=(config.epg_source or "").strip(),
    ))
    return True
