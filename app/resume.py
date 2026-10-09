"""Resume-playback store: remembers where VOD playback stopped.

Positions are keyed by stream URL and persisted as JSON. Entries older
than 90 days are pruned on load so the file never grows unbounded.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_PRUNE_DAYS = 90


def _default_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    return Path(base or ".") / "resume.json"


class ResumeStore:
    """url -> (position_seconds, duration_seconds, saved_at)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _default_path()
        self._data: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        cutoff = datetime.now() - timedelta(days=_PRUNE_DAYS)
        data: dict[str, dict] = {}
        if isinstance(raw, dict):
            for url, entry in raw.items():
                if not isinstance(entry, dict):
                    continue
                try:
                    saved = datetime.fromisoformat(
                        str(entry.get("saved_at", "")))
                except ValueError:
                    continue
                if saved >= cutoff:
                    data[str(url)] = entry
        self._data = data
        if isinstance(raw, dict) and len(data) != len(raw):
            self._persist()  # write back the pruned view

    def save(self, url: str, position: float, duration: float) -> None:
        """Remember a playback position (ignored for trivial positions)."""
        if not url or position <= 0:
            return
        self._data[url] = {
            "position": float(position),
            "duration": float(duration or 0),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._persist()

    def position_for(self, url: str) -> tuple[float, float] | None:
        """Return (position, duration) in seconds, or None if unknown."""
        entry = self._data.get(url)
        if not entry:
            return None
        try:
            return (float(entry.get("position", 0)),
                    float(entry.get("duration", 0)))
        except (TypeError, ValueError):
            return None

    def all(self) -> dict[str, dict]:
        """Return a copy of all active resume points."""
        return dict(self._data)

    def update(self, url: str, pos_s: float, dur_s: float, channel_name: str = "") -> None:
        """Insert or update a resume playback timestamp."""
        self.save(url, pos_s, dur_s)

    def clear(self, url: str) -> None:
        if url in self._data:
            del self._data[url]
            self._persist()

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError:
            pass  # resume data is best-effort; never crash the app
