"""Favorites persistence (simple JSON store)."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def _default_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    return Path(base or ".") / "favorites.json"


class FavoritesStore:
    """Set of favorite channel URLs persisted as JSON."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _default_path()
        self._favs: set[str] = set()
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._favs = set(data) if isinstance(data, list) else set()
        except (OSError, json.JSONDecodeError):
            self._favs = set()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(sorted(self._favs), indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # favorites are best-effort; never crash the app

    def is_favorite(self, channel_url: str) -> bool:
        return channel_url in self._favs

    def toggle(self, channel_url: str) -> bool:
        """Toggle and return the new state (True == now a favorite)."""
        if channel_url in self._favs:
            self._favs.discard(channel_url)
            state = False
        else:
            self._favs.add(channel_url)
            state = True
        self.save()
        return state

    def add(self, channel_url: str) -> None:
        """Add channel to favorites."""
        self._favs.add(channel_url)
        self.save()

    def remove(self, channel_url: str) -> None:
        """Remove channel from favorites."""
        self._favs.discard(channel_url)
        self.save()

    def all(self) -> set[str]:
        return set(self._favs)
