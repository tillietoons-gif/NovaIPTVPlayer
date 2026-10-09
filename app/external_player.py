"""Helper to detect and launch streams in external players (VLC, MPV, etc.)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_vlc() -> str | None:
    found = shutil.which("vlc")
    if found:
        return found
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "VideoLAN" / "VLC" / "vlc.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "VideoLAN" / "VLC" / "vlc.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    return None


def find_mpv() -> str | None:
    found = shutil.which("mpv")
    if found:
        return found
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "mpv" / "mpv.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "mpv" / "mpv.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    return None


def find_potplayer() -> str | None:
    found = shutil.which("PotPlayer64") or shutil.which("PotPlayer")
    if found:
        return found
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "DAUM" / "PotPlayer" / "PotPlayer64.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "DAUM" / "PotPlayer" / "PotPlayer.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    return None


def detect_players() -> dict[str, str]:
    """Return dictionary of available player names -> executable paths."""
    players = {}
    vlc = find_vlc()
    if vlc:
        players["VLC"] = vlc
    mpv = find_mpv()
    if mpv:
        players["MPV"] = mpv
    pot = find_potplayer()
    if pot:
        players["PotPlayer"] = pot
    return players


def launch_player(url: str, title: str = "", player_choice: str = "auto") -> tuple[bool, str]:
    """Launch url in external player. Returns (success, status_message)."""
    if not url:
        return False, "Stream URL is empty"

    players = detect_players()
    exe = None
    player_name = "Player"

    if player_choice.lower() == "vlc" and "VLC" in players:
        exe = players["VLC"]
        player_name = "VLC"
    elif player_choice.lower() == "mpv" and "MPV" in players:
        exe = players["MPV"]
        player_name = "MPV"
    elif player_choice.lower() == "potplayer" and "PotPlayer" in players:
        exe = players["PotPlayer"]
        player_name = "PotPlayer"
    elif players:
        if "VLC" in players:
            player_name, exe = "VLC", players["VLC"]
        else:
            player_name, exe = next(iter(players.items()))

    if exe:
        try:
            args = [exe, url]
            if player_name == "VLC" and title:
                args.append(f"--meta-title={title}")
            elif player_name == "MPV" and title:
                args.append(f"--force-media-title={title}")
            subprocess.Popen(args)
            return True, f"Launched in {player_name}: {title or url}"
        except Exception as exc:
            return False, f"Failed to start {player_name}: {exc}"

    # Fallback to Windows default file association
    if sys.platform == "win32":
        try:
            os.startfile(url)
            return True, f"Opened in system default player: {title or url}"
        except Exception as exc:
            return False, f"Could not launch stream: {exc}"

    return False, "No external media player found (install VLC or MPV)."
