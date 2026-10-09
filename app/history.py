"""Playback history persistence (JSON store)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from app.models import HistoryEntry

_MAX_HISTORY = 50


def _default_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    return Path(base or ".") / "history.json"


class HistoryStore:
    """List of recently played channels persisted as JSON."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _default_path()
        self._entries: list[HistoryEntry] = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._entries = []
            return
        entries: list[HistoryEntry] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("channel_url", "") or "")
                name = str(item.get("channel_name", "") or "")
                if not url:
                    continue
                try:
                    played_at = datetime.fromisoformat(str(item.get("played_at", "")))
                except ValueError:
                    played_at = datetime.now()
                entries.append(HistoryEntry(
                    channel_url=url,
                    channel_name=name,
                    played_at=played_at,
                ))
        self._entries = entries[:_MAX_HISTORY]

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {
                    "channel_url": e.channel_url,
                    "channel_name": e.channel_name,
                    "played_at": e.played_at.isoformat(timespec="seconds"),
                }
                for e in self._entries
            ]
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass  # best-effort persistence

    def all(self) -> list[HistoryEntry]:
        return list(self._entries)

    def add(self, channel_name: str, channel_url: str) -> None:
        if not channel_url:
            return
        self._entries = [e for e in self._entries if e.channel_url != channel_url]
        self._entries.insert(0, HistoryEntry(
            channel_url=channel_url,
            channel_name=channel_name or "Unknown Channel",
            played_at=datetime.now(),
        ))
        self._entries = self._entries[:_MAX_HISTORY]
        self.save()

    def record(self, channel_url: str, channel_name: str = "") -> None:
        """Alias for add(channel_name, channel_url)."""
        self.add(channel_name, channel_url)

    def clear(self) -> None:
        self._entries = []
        self.save()
