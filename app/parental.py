"""Parental controls: PIN-protected channel categories.

The PIN is stored as a SHA-256 hash in QSettings -- never as plaintext.
Locked categories are category (group) names; unlocking is per-session,
so locks re-engage automatically when the app restarts.
"""

from __future__ import annotations

import hashlib
import re

from PySide6.QtCore import QSettings

from app import __app_name__

_PIN_RE = re.compile(r"^\d{4,8}$")


def _hash(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


class ParentalControls:
    """PIN + locked-category store with a session unlock cache."""

    def __init__(self) -> None:
        self._s = QSettings(__app_name__, __app_name__)
        self._unlocked: set[str] = set()  # session-only; cleared on restart

    # -- PIN ------------------------------------------------------------------
    @staticmethod
    def valid_pin(pin: str) -> bool:
        """A PIN is 4-8 ASCII digits."""
        return bool(_PIN_RE.match(pin or ""))

    def has_pin(self) -> bool:
        return bool(self._s.value("parental/pin_hash", ""))

    def set_pin(self, pin: str) -> None:
        if not self.valid_pin(pin):
            raise ValueError("PIN must be 4-8 digits.")
        self._s.setValue("parental/pin_hash", _hash(pin))
        self._s.sync()

    def verify(self, pin: str) -> bool:
        stored = str(self._s.value("parental/pin_hash", ""))
        return bool(stored) and stored == _hash(pin or "")

    def change_pin(self, old: str, new: str) -> bool:
        """Change the PIN; returns False when the old PIN is wrong."""
        if not self.verify(old):
            return False
        self.set_pin(new)
        return True

    def clear(self) -> None:
        """Remove the PIN and all locked categories."""
        self._s.remove("parental/pin_hash")
        self._s.remove("parental/locked")
        self._unlocked.clear()
        self._s.sync()

    # -- locked categories ------------------------------------------------------
    def locked_groups(self) -> set[str]:
        raw = self._s.value("parental/locked", [])
        if isinstance(raw, (list, tuple, set)):
            return {str(g) for g in raw if g}
        return set()

    def set_locked_groups(self, groups) -> None:
        self._s.setValue("parental/locked", sorted({str(g) for g in groups}))
        # keep session unlocks consistent with the new lock set
        self._unlocked &= self.locked_groups()
        self._s.sync()

    def is_locked(self, group: str) -> bool:
        return bool(group) and group in self.locked_groups()

    # -- session unlocks ----------------------------------------------------------
    def unlock_group(self, group: str) -> None:
        self._unlocked.add(group)

    def is_unlocked(self, group: str) -> bool:
        return group in self._unlocked

    def lock_all(self) -> None:
        """Re-engage every lock for this session."""
        self._unlocked.clear()
