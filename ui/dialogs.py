"""Dialogs: add-playlist wizard, settings, and parental PIN prompts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTabWidget, QWidget, QSpinBox,
    QFormLayout, QDialogButtonBox, QCheckBox, QListWidget,
    QListWidgetItem, QMessageBox, QGridLayout, QComboBox,
)

from app.backup import export_backup, import_backup
from app.favorites import FavoritesStore
from app.history import HistoryStore
from app.profiles import ProfileStore
from app.resume import ResumeStore
from ui.theme import UiPrefs


class AddPlaylistDialog(QDialog):
    """Collect an M3U source (URL or file) plus an optional XMLTV source."""

    def __init__(self, playlist: str = "", epg: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add playlist")
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)

        tabs = QTabWidget()
        # --- URL tab ---
        url_tab = QWidget()
        url_form = QFormLayout(url_tab)
        self.url_edit = QLineEdit(playlist if playlist.startswith("http") else "")
        self.url_edit.setPlaceholderText("https://example.com/playlist.m3u8")
        url_form.addRow("Playlist URL:", self.url_edit)
        tabs.addTab(url_tab, "From URL")
        # --- File tab ---
        file_tab = QWidget()
        file_lay = QHBoxLayout(file_tab)
        self.file_edit = QLineEdit(
            playlist if playlist and not playlist.startswith("http") else ""
        )
        self.file_edit.setPlaceholderText("C:\\playlists\\mylist.m3u")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        file_lay.addWidget(self.file_edit, 1)
        file_lay.addWidget(browse)
        tabs.addTab(file_tab, "From file")
        lay.addWidget(tabs)

        epg_form = QFormLayout()
        self.epg_edit = QLineEdit(epg)
        self.epg_edit.setPlaceholderText("https://example.com/epg.xml (optional)")
        epg_form.addRow("XMLTV guide:", self.epg_edit)
        lay.addLayout(epg_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open playlist", str(Path.home()),
            "Playlists (*.m3u *.m3u8);;All files (*)",
        )
        if path:
            self.file_edit.setText(path)

    def playlist_source(self) -> str:
        if self.url_edit.text().strip():
            return self.url_edit.text().strip()
        return self.file_edit.text().strip()

    def epg_source(self) -> str:
        return self.epg_edit.text().strip()


class SettingsDialog(QDialog):
    """Playback / UI preferences."""

    SHORTCUTS = [
        ("Space", "Play / pause"),
        ("F", "Fullscreen"),
        ("P", "Picture-in-Picture"),
        ("A", "Aspect ratio"),
        ("C / S", "Audio & Subtitle tracks"),
        ("[ / ]", "Subtitle sync offset (±250ms)"),
        ("Z / Enter", "Quick Channel Zapper overlay"),
        ("I", "Stream Diagnostics HUD (Stats for Nerds)"),
        ("T", "Sleep Timer selector"),
        ("0–9", "Direct channel number tuning"),
        ("E", "External player"),
        ("M", "Mute / unmute"),
        ("Left / Right", "Previous / next channel"),
        ("Ctrl+K / /", "Quick spotlight search"),
        ("Esc", "Close panel or dialog"),
    ]

    def __init__(self, config, parent=None, parental=None, groups=None,
                 profiles=None, favorites=None, history=None, resume=None) -> None:
        super().__init__(parent)
        self._config = config
        self._prefs = UiPrefs()
        self._parental = parental
        self._groups = sorted(groups or [])
        self._profiles = profiles or getattr(parent, "profiles", None) or ProfileStore()
        self._favorites = favorites or getattr(parent, "favorites", None) or FavoritesStore()
        self._history = history or getattr(parent, "history", None) or HistoryStore()
        self._resume = resume or getattr(parent, "resume", None) or ResumeStore()

        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)

        lay = QVBoxLayout(self)
        form = QFormLayout()

        # Playback & Audio
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(0, 125)
        self.volume_spin.setValue(config.volume)
        form.addRow("Default volume:", self.volume_spin)

        self.mute_check = QCheckBox("Start muted")
        self.mute_check.setChecked(config.muted)
        form.addRow(self.mute_check)

        # Hardware Acceleration (GPU)
        self.hw_combo = QComboBox()
        self.hw_combo.addItem("Auto (Direct3D 11 / DXVA2 Fallback)", "auto")
        self.hw_combo.addItem("Direct3D 11 (D3D11VA - Recommended)", "d3d11va")
        self.hw_combo.addItem("DirectX Video Accel (DXVA2)", "dxva2")
        self.hw_combo.addItem("NVIDIA NVDEC (CUDA)", "cuda")
        self.hw_combo.addItem("Intel Quick Sync Video (QSV)", "qsv")
        self.hw_combo.addItem("Software Decoding (Off)", "off")
        cur_hw = getattr(config, "hw_acceleration", "auto")
        hw_idx = self.hw_combo.findData(cur_hw)
        if hw_idx >= 0:
            self.hw_combo.setCurrentIndex(hw_idx)
        self.hw_combo.setToolTip("GPU Hardware Acceleration enables smooth 4K 60fps playback with ultra-low CPU load.")
        form.addRow("GPU Acceleration:", self.hw_combo)

        # Audio Dialogue Boost / Dynamic Compressor
        self.audio_combo = QComboBox()
        self.audio_combo.addItem("Off (Original stream audio)", "off")
        self.audio_combo.addItem("Dialogue Enhancer (Clear speech vocal lift)", "dialogue")
        self.audio_combo.addItem("Night Mode (Dynamic compressor & quiet bass)", "night")
        cur_ab = getattr(config, "audio_boost", "off")
        ab_idx = self.audio_combo.findData(cur_ab)
        if ab_idx >= 0:
            self.audio_combo.setCurrentIndex(ab_idx)
        self.audio_combo.setToolTip("DSP dynamic range compressor enhances speech intelligibility and limits sudden loud explosions.")
        form.addRow("Audio Dialogue Boost:", self.audio_combo)

        self.anim_check = QCheckBox("Reduce animations")
        self.anim_check.setChecked(self._prefs.reduce_animations)
        self.anim_check.setToolTip(
            "Disable page transitions, drawer slides and shimmer effects.")
        form.addRow(self.anim_check)

        lay.addLayout(form)

        # Backup & Restore Section
        bk_title = QLabel("Backup & Restore (.novabackup)")
        bk_title.setStyleSheet("font-weight:700; margin-top:8px;")
        lay.addWidget(bk_title)

        bk_desc = QLabel("Export or restore all provider accounts, playlists, favorites, and playback settings.")
        bk_desc.setStyleSheet("color:#8b91a7; font-size:11px;")
        bk_desc.setWordWrap(True)
        lay.addWidget(bk_desc)

        bk_row = QHBoxLayout()
        bk_row.setSpacing(10)
        export_btn = QPushButton("  Export Backup (.novabackup)…")
        export_btn.clicked.connect(self._export_backup)
        bk_row.addWidget(export_btn)
        import_btn = QPushButton("  Restore from Backup…")
        import_btn.clicked.connect(self._import_backup)
        bk_row.addWidget(import_btn)
        lay.addLayout(bk_row)

        if self._parental is not None:
            pc_title = QLabel("Parental Controls")
            pc_title.setStyleSheet("font-weight:700; margin-top:6px;")
            lay.addWidget(pc_title)
            self._pc_box = QVBoxLayout()
            self._pc_box.setSpacing(6)
            lay.addLayout(self._pc_box)
            self._refresh_parental_ui()

        sc_title = QLabel("Keyboard shortcuts")
        sc_title.setStyleSheet("font-weight:700; margin-top:6px;")
        lay.addWidget(sc_title)
        sc_form = QFormLayout()
        sc_form.setSpacing(4)
        for keys, desc in self.SHORTCUTS:
            k = QLabel(keys)
            k.setStyleSheet(
                "background:#1a1f2b; border:1px solid #232b3d; "
                "border-radius:6px; padding:3px 10px; font-weight:600;")
            d = QLabel(desc)
            d.setStyleSheet("color:#8b91a7;")
            sc_form.addRow(k, d)
        lay.addLayout(sc_form)

        note = QLabel(
            "Tip: playback uses the built-in hardware accelerated engine\n"
            "— D3D11 / DXVA2 GPU decoders ensure stutter-free 4K streaming."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#8b95a9; font-size:11px;")
        lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _export_backup(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"NovaIPTV_Backup_{stamp}.novabackup"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Backup", str(Path.home() / default_name),
            "Nova Backup (*.novabackup);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            saved = export_backup(
                path, self._config, self._profiles, self._favorites,
                self._history, self._resume
            )
            QMessageBox.information(
                self, "Backup Exported",
                f"Backup successfully saved to:\n{saved.name}\n\n"
                "Includes all provider profiles, favorites, history, and settings.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not create backup:\n{exc}")

    def _import_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore Backup", str(Path.home()),
            "Nova Backup (*.novabackup *.json);;All Files (*)",
        )
        if not path:
            return
        answer = QMessageBox.question(
            self, "Restore Backup",
            "Restoring a backup will merge and update your profiles, favorites, "
            "and playback preferences.\n\nDo you want to continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            res = import_backup(
                path, self._config, self._profiles, self._favorites,
                self._history, self._resume
            )
            self.volume_spin.setValue(self._config.volume)
            self.mute_check.setChecked(self._config.muted)
            hw_idx = self.hw_combo.findData(self._config.hw_acceleration)
            if hw_idx >= 0:
                self.hw_combo.setCurrentIndex(hw_idx)
            ab_idx = self.audio_combo.findData(self._config.audio_boost)
            if ab_idx >= 0:
                self.audio_combo.setCurrentIndex(ab_idx)

            QMessageBox.information(
                self, "Backup Restored",
                f"Backup successfully restored!\n\n"
                f"• Profiles imported: {res.get('profiles', 0)}\n"
                f"• Favorites restored: {res.get('favorites', 0)}\n"
                f"• History records: {res.get('history', 0)}\n"
                f"• Resume points: {res.get('resume', 0)}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", f"Could not restore backup:\n{exc}")

    # -- parental controls ------------------------------------------------------
    @staticmethod
    def _pin_edit() -> QLineEdit:
        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.Password)
        edit.setMaxLength(8)
        edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,8}")))
        edit.setPlaceholderText("4–8 digits")
        return edit

    def _clear_box(self, box) -> None:
        while box.count():
            item = box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _refresh_parental_ui(self) -> None:
        """Rebuild the parental section for the current PIN state."""
        self._clear_box(self._pc_box)
        p = self._parental
        if p.has_pin():
            row = QHBoxLayout()
            row.addWidget(QLabel("A PIN is set."))
            row.addStretch(1)
            change_btn = QPushButton("Change PIN…")
            change_btn.clicked.connect(self._change_pin)
            row.addWidget(change_btn)
            remove_btn = QPushButton("Remove PIN")
            remove_btn.clicked.connect(self._remove_pin)
            row.addWidget(remove_btn)
            self._pc_box.addLayout(row)
            self.new_pin_edit = None
            self.confirm_pin_edit = None
        else:
            form = QFormLayout()
            self.new_pin_edit = self._pin_edit()
            self.confirm_pin_edit = self._pin_edit()
            self.new_pin_edit.textChanged.connect(self._maybe_enable_locks)
            self.confirm_pin_edit.textChanged.connect(self._maybe_enable_locks)
            form.addRow("New PIN:", self.new_pin_edit)
            form.addRow("Confirm PIN:", self.confirm_pin_edit)
            self._pc_box.addLayout(form)

        self._pc_box.addWidget(QLabel("Locked categories:"))
        self.lock_list = QListWidget()
        self.lock_list.setMaximumHeight(140)
        locked = p.locked_groups()
        for g in self._groups:
            item = QListWidgetItem(g)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if g in locked else Qt.Unchecked)
            self.lock_list.addItem(item)
        self.lock_list.setEnabled(p.has_pin())
        self._pc_box.addWidget(self.lock_list)
        if not p.has_pin():
            hint = QLabel("Set a PIN above to lock categories.")
            hint.setStyleSheet("color:#8b95a9; font-size:11px;")
            self._pc_box.addWidget(hint)

    def _maybe_enable_locks(self) -> None:
        """Enable the checklist as soon as a plausible PIN is typed."""
        if (self.new_pin_edit is not None
                and len(self.new_pin_edit.text()) >= 4
                and self.new_pin_edit.text() == self.confirm_pin_edit.text()):
            self.lock_list.setEnabled(True)

    def _change_pin(self) -> None:
        dlg = _ChangePinDialog(self._parental, self)
        dlg.exec()

    def _remove_pin(self) -> None:
        answer = QMessageBox.question(
            self, "Remove PIN",
            "Remove the parental PIN and unlock all categories?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._parental.clear()
            self._refresh_parental_ui()

    def _save_parental(self) -> bool:
        """Apply parental changes. Returns False when saving must abort."""
        p = self._parental
        if not p.has_pin() and self.new_pin_edit is not None:
            pin = self.new_pin_edit.text().strip()
            confirm = self.confirm_pin_edit.text().strip()
            if pin or confirm:
                if pin != confirm:
                    QMessageBox.warning(
                        self, "Parental Controls",
                        "The PIN entries do not match.")
                    return False
                try:
                    p.set_pin(pin)
                except ValueError as exc:
                    QMessageBox.warning(
                        self, "Parental Controls", str(exc))
                    return False
        locked = set()
        for i in range(self.lock_list.count()):
            item = self.lock_list.item(i)
            if item.checkState() == Qt.Checked:
                locked.add(item.text())
        p.set_locked_groups(locked)
        return True

    def _save(self) -> None:
        if self._parental is not None and not self._save_parental():
            return
        self._config.hw_acceleration = self.hw_combo.currentData()
        self._config.audio_boost = self.audio_combo.currentData()
        self._config.volume = self.volume_spin.value()
        self._config.muted = self.mute_check.isChecked()
        self._config.sync()
        self._prefs.reduce_animations = self.anim_check.isChecked()
        self._prefs.sync()
        self.accept()


class PinDialog(QDialog):
    """Ask for the parental PIN. Accepts only when *verify* approves.

    A wrong PIN shows an error and clears the field -- no hints, no
    lockout counter; the dialog simply stays open.
    """

    def __init__(self, verify, parent=None, subtitle: str = "") -> None:
        super().__init__(parent)
        self._verify = verify
        self.setWindowTitle("Parental PIN")
        self.setMinimumWidth(300)

        lay = QVBoxLayout(self)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            lay.addWidget(sub)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setMaxLength(8)
        self.edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,8}")))
        self.edit.setPlaceholderText("Enter PIN")
        self.edit.returnPressed.connect(self._check)
        lay.addWidget(self.edit)
        self.error = QLabel("")
        self.error.setObjectName("pinError")
        lay.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.edit.setFocus()

    def _check(self) -> None:
        if self._verify(self.edit.text()):
            self.accept()
        else:
            self.error.setText("Incorrect PIN. Try again.")
            self.edit.clear()
            self.edit.setFocus()


class _ChangePinDialog(QDialog):
    """Change an existing parental PIN (old + new + confirm)."""

    def __init__(self, parental, parent=None) -> None:
        super().__init__(parent)
        self._parental = parental
        self.setWindowTitle("Change PIN")
        self.setMinimumWidth(300)

        form = QFormLayout(self)
        self.old_edit = SettingsDialog._pin_edit()
        self.new_edit = SettingsDialog._pin_edit()
        self.confirm_edit = SettingsDialog._pin_edit()
        form.addRow("Current PIN:", self.old_edit)
        form.addRow("New PIN:", self.new_edit)
        form.addRow("Confirm new PIN:", self.confirm_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _apply(self) -> None:
        old = self.old_edit.text().strip()
        new = self.new_edit.text().strip()
        confirm = self.confirm_edit.text().strip()
        if new != confirm:
            QMessageBox.warning(self, "Change PIN",
                                "The new PIN entries do not match.")
            return
        try:
            ok = self._parental.change_pin(old, new)
        except ValueError as exc:
            QMessageBox.warning(self, "Change PIN", str(exc))
            return
        if not ok:
            QMessageBox.warning(self, "Change PIN",
                                "The current PIN is incorrect.")
            return
        self.accept()


class ShortcutsDialog(QDialog):
    """Clean reference cheat-sheet for keyboard shortcuts."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setObjectName("shortcutsDialog")
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(14)

        title = QLabel("Keyboard Shortcuts")
        title.setObjectName("dlgTitle")
        lay.addWidget(title)

        sub = QLabel("Quickly navigate, control playback, and adjust volume:")
        sub.setObjectName("cardMeta")
        lay.addWidget(sub)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)

        shortcuts = [
            ("Space", "Play / Pause stream"),
            ("F", "Toggle Fullscreen mode"),
            ("Z / Enter", "Quick Channel Zapper overlay"),
            ("I", "Stream Diagnostics HUD (Stats for Nerds)"),
            ("T", "Sleep Timer selector"),
            ("0–9", "Direct channel number tuning"),
            ("P", "Picture-in-Picture (PiP) floating player"),
            ("A", "Cycle Aspect Ratio (Auto / 16:9 / 4:3 / Fill)"),
            ("C / S", "Audio & Subtitle track selector"),
            ("[ / ]", "Subtitle sync offset (±250ms delay)"),
            ("E", "Launch in External Player (VLC / MPV)"),
            ("M", "Mute / Unmute audio"),
            ("↑ / ↓", "Volume up / down (±5%)"),
            ("← / →", "Prev / Next channel (or Seek ±10s in VOD)"),
            ("Ctrl+K / /", "Quick spotlight search"),
            ("[", "Toggle sidebar collapse / icon rail"),
            ("Esc", "Exit Fullscreen / Close drawer / Cancel"),
            ("? / F1", "Show this shortcuts help dialog"),
        ]

        for row, (key_label, desc) in enumerate(shortcuts):
            k_box = QLabel(key_label)
            k_box.setObjectName("keyBadge")
            k_box.setAlignment(Qt.AlignCenter)
            d_lbl = QLabel(desc)
            d_lbl.setObjectName("keyDesc")
            grid.addWidget(k_box, row, 0, Qt.AlignLeft)
            grid.addWidget(d_lbl, row, 1, Qt.AlignVCenter)

        lay.addLayout(grid)
        lay.addSpacing(6)

        btn = QPushButton("Got it")
        btn.setObjectName("primaryBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, 0, Qt.AlignRight)
