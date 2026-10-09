from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.epg import EPGManager
from app.history import HistoryStore
from app.models import HistoryEntry, xtream_series_to_channels
from app.player import Player, _DecodeWorker
from app.profiles import ProviderProfile


class TestCoreFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_profile_redacted_calls_is_xtream(self) -> None:
        p = ProviderProfile(
            id="test-xtream",
            name="My Xtream",
            kind="xtream",
            server="http://example.com:8080",
            username="myuser",
            password="secretpassword",
        )
        self.assertTrue(p.is_xtream())
        redacted = p.redacted()
        self.assertIn("myuser@http://example.com:8080", redacted)
        self.assertNotIn("secretpassword", redacted)

    def test_config_muted_boolean_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = str(Path(tmpdir) / "test_settings.ini")
            qs = QSettings(settings_path, QSettings.IniFormat)
            qs.setValue("player/muted", "false")
            qs.sync()

            cfg = AppConfig()
            cfg._s = qs
            # In QSettings on Windows/IniFormat, 'false' string would be truthy without type=bool
            self.assertFalse(cfg.muted)

            qs.setValue("player/muted", True)
            qs.sync()
            self.assertTrue(cfg.muted)

    def test_xmltv_parsing_without_space_in_timezone(self) -> None:
        tvxml = '''<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="chan1">
    <display-name>BBC One</display-name>
  </channel>
  <programme start="20240102100000+0000" stop="20240102120000+0000" channel="chan1">
    <title>Morning Show</title>
  </programme>
</tv>
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "guide_nospace.xml"
            path.write_text(tvxml, encoding="utf-8")

            manager = EPGManager()
            count = manager.load(str(path))
            self.assertEqual(count, 1)

            now = datetime(2024, 1, 2, 11, 0, tzinfo=timezone.utc)
            current, _ = manager.now_and_next("chan1", now=now)
            self.assertIsNotNone(current)
            self.assertEqual(current.title, "Morning Show")

    def test_xtream_series_unique_urls(self) -> None:
        series_data = [
            {"id": "101", "name": "Series One"},
            {"id": "102", "name": "Series Two"},
        ]
        channels = xtream_series_to_channels(None, series_data, "prov1")
        self.assertEqual(len(channels), 2)
        self.assertEqual(channels[0].url, "xtream://series/101")
        self.assertEqual(channels[1].url, "xtream://series/102")
        self.assertNotEqual(channels[0].url, channels[1].url)


class TestHistoryStore(unittest.TestCase):
    def test_history_persistence_and_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "history.json"
            store = HistoryStore(path=store_path)

            store.add("Channel 1", "http://stream/1")
            store.add("Channel 2", "http://stream/2")
            store.add("Channel 1", "http://stream/1")  # re-add brings to front

            entries = store.all()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0].channel_name, "Channel 1")
            self.assertEqual(entries[0].channel_url, "http://stream/1")
            self.assertEqual(entries[1].channel_name, "Channel 2")

            # Reload from disk in a fresh store instance
            store2 = HistoryStore(path=store_path)
            entries2 = store2.all()
            self.assertEqual(len(entries2), 2)
            self.assertEqual(entries2[0].channel_name, "Channel 1")
            self.assertIsInstance(entries2[0], HistoryEntry)

            # Test clear
            store2.clear()
            self.assertEqual(len(store2.all()), 0)


class TestPlayerSignalsAndWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_signals_disconnected_on_stop(self) -> None:
        player = Player()
        worker = _DecodeWorker("http://example.com/test", 100, False, {})
        player._worker = worker
        player._worker_connections = [
            worker.state_changed.connect(player.state_changed.emit),
        ]

        signal_received = []
        player.state_changed.connect(lambda s: signal_received.append(s))

        # Stop player - should disconnect worker signals so worker doesn't emit to player
        player.stop()
        self.assertIsNone(player._worker)

        # Emitting state_changed on worker should not affect player anymore
        worker.state_changed.emit("playing")
        self.assertNotIn("playing", signal_received)


class TestFullscreenVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_fullscreen_controls_and_back_button(self) -> None:
        from PySide6.QtWidgets import QWidget
        from ui.main_window import _FullscreenVideo
        from app.models import Channel
        from app.player import Player

        class DummyMain(QWidget):
            def __init__(self):
                super().__init__()
                self.player = Player()
                self._current_channel = Channel(name="Test News HD", url="http://test/1", group="News", kind="live")
                self._player_state = "playing"
                self.config = AppConfig()
                self.epg = EPGManager()
                self._muted = False
            def _toggle_pause(self): pass
            def _play_prev(self): pass
            def _play_next(self): pass
            def _toggle_mute(self): pass
            def _on_volume(self, v): pass

        main = DummyMain()
        fs = _FullscreenVideo(main)
        self.assertIsNotNone(fs.back_btn)
        self.assertIsNotNone(fs.pp_btn)
        self.assertIsNotNone(fs.prev_btn)
        self.assertIsNotNone(fs.next_btn)
        self.assertIsNotNone(fs.vol_slider)
        self.assertEqual(fs.title_label.text(), "Test News HD")
        self.assertTrue(fs.live_badge.isVisible())

        fs.back_btn.click()
        self.assertEqual(fs.result(), _FullscreenVideo.Accepted)
        fs.deleteLater()
        main.deleteLater()

    def test_ui_ux_enhancements(self):
        """Test LogoLabel caching, ShortcutsDialog, and new icon generation."""
        from app.models import Channel
        from ui.widgets import LogoLabel, _IMAGE_CACHE, make_icon, ChannelCard
        from ui.dialogs import ShortcutsDialog
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QPoint

        # 1. Test vector icon generation for new/updated icons
        for icon_name in ("help", "question", "volume", "mute", "back", "compress"):
            icon = make_icon(icon_name, 20)
            self.assertFalse(icon.isNull())

        # 2. Test ShortcutsDialog
        dlg = ShortcutsDialog()
        self.assertIsNotNone(dlg)
        dlg.deleteLater()

        # 3. Test LogoLabel in-memory image cache
        logo = LogoLabel(48)
        dummy_img = QImage(48, 48, QImage.Format_RGB32)
        dummy_img.fill(0xFF00FF)
        test_url = "http://example.com/channel_logo.png"
        _IMAGE_CACHE[test_url] = dummy_img
        logo.load(test_url)
        # Should render immediately from cache without starting network loader
        self.assertIsNone(logo._loader)
        logo.deleteLater()

        # 4. Test ChannelCard context menu requested signal
        ch = Channel(name="Test Channel", url="http://test.com/stream.m3u8")
        card = ChannelCard(ch)
        received = []
        card.context_menu_requested.connect(lambda c, pos: received.append((c, pos)))
        card.context_menu_requested.emit(ch, QPoint(100, 200))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0].name, "Test Channel")
        card.deleteLater()


if __name__ == "__main__":
    unittest.main()

