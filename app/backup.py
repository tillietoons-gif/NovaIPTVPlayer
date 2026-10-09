"""Backup and Restore module for Nova IPTV Player.

Exports and imports user profiles, favorites, configuration, watch history,
and resume playback timestamps into a single portable `.novabackup` file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import AppConfig
from app.favorites import FavoritesStore
from app.history import HistoryStore
from app.profiles import ProfileStore, ProviderProfile
from app.resume import ResumeStore


def create_backup_data(
    config: AppConfig,
    profiles: ProfileStore,
    favorites: FavoritesStore,
    history: HistoryStore,
    resume: ResumeStore,
) -> dict[str, Any]:
    """Assemble all application state into a serialized dictionary."""
    profiles_data = [p.to_dict() for p in profiles.all()]
    favs_data = sorted(favorites.all())
    history_data = [
        {
            "channel_url": e.channel_url,
            "channel_name": e.channel_name,
            "played_at": e.played_at.isoformat(),
        }
        for e in history.all()
    ]
    resume_data = {url: pt.to_dict() for url, pt in resume.all().items()}
    config_data = {
        "volume": config.volume,
        "default_aspect": config.default_aspect,
        "external_player": config.external_player,
        "external_player_path": config.external_player_path,
        "user_agent": config.user_agent,
        "record_directory": config.record_directory,
        "hw_acceleration": getattr(config, "hw_acceleration", "auto"),
        "audio_boost": getattr(config, "audio_boost", "off"),
    }

    return {
        "format": "nova_iptv_backup",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profiles": profiles_data,
        "favorites": favs_data,
        "history": history_data,
        "resume": resume_data,
        "config": config_data,
    }


def export_backup(
    dest_path: str | Path,
    config: AppConfig,
    profiles: ProfileStore,
    favorites: FavoritesStore,
    history: HistoryStore,
    resume: ResumeStore,
) -> Path:
    """Save application backup to the specified destination path."""
    dest = Path(dest_path)
    if not dest.name.endswith(".novabackup") and not dest.name.endswith(".json"):
        dest = dest.with_suffix(".novabackup")
    dest.parent.mkdir(parents=True, exist_ok=True)

    data = create_backup_data(config, profiles, favorites, history, resume)
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest


def import_backup(
    src_path: str | Path,
    config: AppConfig,
    profiles: ProfileStore,
    favorites: FavoritesStore,
    history: HistoryStore,
    resume: ResumeStore,
) -> dict[str, int]:
    """Restore application state from a `.novabackup` file.

    Returns a summary dictionary of restored items count.
    """
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup file not found: {src}")

    content = src.read_text(encoding="utf-8")
    data = json.loads(content)

    if not isinstance(data, dict) or data.get("format") != "nova_iptv_backup":
        raise ValueError("Invalid backup format: missing 'nova_iptv_backup' header.")

    # 1. Restore profiles
    profiles_restored = 0
    if "profiles" in data and isinstance(data["profiles"], list):
        for p_dict in data["profiles"]:
            try:
                prof = ProviderProfile.from_dict(p_dict)
                profiles.save(prof)
                profiles_restored += 1
            except Exception:
                continue

    # 2. Restore favorites
    favs_restored = 0
    if "favorites" in data and isinstance(data["favorites"], list):
        for fav_url in data["favorites"]:
            favorites.add(str(fav_url))
            favs_restored += 1

    # 3. Restore config settings
    if "config" in data and isinstance(data["config"], dict):
        cfg = data["config"]
        if "volume" in cfg:
            config.volume = int(cfg["volume"])
        if "default_aspect" in cfg:
            config.default_aspect = str(cfg["default_aspect"])
        if "external_player" in cfg:
            config.external_player = str(cfg["external_player"])
        if "external_player_path" in cfg:
            config.external_player_path = str(cfg["external_player_path"])
        if "user_agent" in cfg:
            config.user_agent = str(cfg["user_agent"])
        if "record_directory" in cfg:
            config.record_directory = str(cfg["record_directory"])
        if "hw_acceleration" in cfg and hasattr(config, "hw_acceleration"):
            config.hw_acceleration = str(cfg["hw_acceleration"])
        if "audio_boost" in cfg and hasattr(config, "audio_boost"):
            config.audio_boost = str(cfg["audio_boost"])
        config.save()

    # 4. Restore history
    history_restored = 0
    if "history" in data and isinstance(data["history"], list):
        for h_entry in data["history"]:
            try:
                history.record(h_entry["channel_url"], h_entry.get("channel_name", ""))
                history_restored += 1
            except Exception:
                continue

    # 5. Restore resume points
    resume_restored = 0
    if "resume" in data and isinstance(data["resume"], dict):
        for url, pt_dict in data["resume"].items():
            try:
                resume.update(
                    url,
                    pos_s=float(pt_dict.get("pos_s", 0)),
                    dur_s=float(pt_dict.get("dur_s", 0)),
                    channel_name=pt_dict.get("channel_name", ""),
                )
                resume_restored += 1
            except Exception:
                continue

    return {
        "profiles": profiles_restored,
        "favorites": favs_restored,
        "history": history_restored,
        "resume": resume_restored,
    }
