"""Unit tests for Advanced IPTV Features Phase 2:
1. Multi-View (Quad-Screen / Split-Screen sports grid)
2. GPU Hardware Acceleration (D3D11 / DXVA2 for 4K 60fps)
3. Catch-Up TV & Replay from EPG (timeshift archive URL generation)
4. Subtitle Sync Offset & Audio Dialogue Boost (dynamic voice compressor)
5. Backup & Restore (.novabackup export and import engine)
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.backup import export_backup, import_backup, create_backup_data
from app.config import AppConfig
from app.favorites import FavoritesStore
from app.history import HistoryStore
from app.models import Channel, EPGProgram
from app.player import Player
from app.playlist import parse_m3u
from app.profiles import ProfileStore, ProviderProfile
from app.resume import ResumeStore
from ui.multiview import MultiViewTile, MultiViewGrid

_app = QApplication.instance() or QApplication(sys.argv)


class TestAdvancedFeaturesV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

        # Isolated config & stores
        self.settings = QSettings(str(self.tmp / "test_config.ini"), QSettings.IniFormat)
        self.config = AppConfig(self.settings)

        self.profiles_path = self.tmp / "test_profiles.json"
        self.profiles = ProfileStore(self.profiles_path)

        self.fav_path = self.tmp / "test_favs.json"
        self.favorites = FavoritesStore(self.fav_path)

        self.hist_path = self.tmp / "test_history.json"
        self.history = HistoryStore(self.hist_path)

        self.resume_path = self.tmp / "test_resume.json"
        self.resume = ResumeStore(self.resume_path)

        self.player = Player()

    def tearDown(self):
        self.player.stop()
        self.temp_dir.cleanup()

    # -- 1. GPU Hardware Acceleration ------------------------------------------
    def test_gpu_hardware_acceleration_settings(self):
        """Player correctly accepts and tracks GPU acceleration modes."""
        self.assertEqual(self.player.hw_acceleration, "auto")
        self.player.set_hw_acceleration("d3d11va")
        self.assertEqual(self.player.hw_acceleration, "d3d11va")
        self.player.set_hw_acceleration("dxva2")
        self.assertEqual(self.player.hw_acceleration, "dxva2")
        self.player.set_hw_acceleration("cuda")
        self.assertEqual(self.player.hw_acceleration, "cuda")
        self.player.set_hw_acceleration("off")
        self.assertEqual(self.player.hw_acceleration, "off")

        # Verify media_info reflects hw acceleration
        info = self.player.media_info()
        self.assertIn("hw_accel", info)
        self.assertEqual(info["hw_accel"], "off")

    # -- 2. Subtitle Sync Offset & Audio Dialogue Boost ------------------------
    def test_subtitle_sync_offset_control(self):
        """Player allows shifting subtitle timing in milliseconds."""
        self.assertEqual(self.player.subtitle_offset_ms, 0)
        self.player.set_subtitle_offset(500)
        self.assertEqual(self.player.subtitle_offset_ms, 500)
        self.player.set_subtitle_offset(-750)
        self.assertEqual(self.player.subtitle_offset_ms, -750)

    def test_audio_dialogue_boost_dsp(self):
        """Player tracks dialogue boost and night mode dynamic compressor settings."""
        self.assertEqual(self.player.audio_boost, "off")
        self.player.set_audio_boost("dialogue")
        self.assertEqual(self.player.audio_boost, "dialogue")
        self.player.set_audio_boost("night")
        self.assertEqual(self.player.audio_boost, "night")

        info = self.player.media_info()
        self.assertIn("audio_boost", info)
        self.assertEqual(info["audio_boost"], "night")

    # -- 3. Catch-Up TV & Replay from EPG ---------------------------------------
    def test_channel_catchup_metadata_and_url_generation(self):
        """Channel model correctly parses catch-up flags and formats replay URLs."""
        # 1. Append catchup format (e.g. ?utc=...)
        ch1 = Channel(
            id="ch1",
            name="BBC One",
            url="http://iptv.example.com/live/bbc1.m3u8",
            catchup="append",
            catchup_days=7,
            catchup_source="?utc=${start}&lutc=${timestamp}",
        )
        self.assertTrue(ch1.catchup)
        self.assertEqual(ch1.catchup_days, 7)
        dt = datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)
        url1 = ch1.build_catchup_url(dt, duration_minutes=60)
        self.assertIn("utc=", url1)
        self.assertIn("lutc=", url1)
        self.assertTrue(url1.startswith("http://iptv.example.com/live/bbc1.m3u8?utc="))

        # 2. Shift/Flussonic catchup format
        ch2 = Channel(
            id="ch2",
            name="Sky Sports",
            url="http://stream.example.com/live/skysports/tracks-v1a1/mono.m3u8",
            catchup="flussonic",
        )
        url2 = ch2.build_catchup_url(dt, duration_minutes=90)
        self.assertIn("timeshift_rel", url2)

    def test_m3u_catchup_parsing(self):
        """M3U parser reads catchup, catchup-days, and catchup-source attributes."""
        m3u_content = """#EXTM3U
#EXTINF:-1 tvg-id="espn.us" catchup="append" catchup-days="5" catchup-source="?timeshift=${start}&duration=${duration}",ESPN HD
http://live.example.com/espn.m3u8
"""
        channels = parse_m3u(m3u_content)
        self.assertEqual(len(channels), 1)
        ch = channels[0]
        self.assertTrue(ch.catchup)
        self.assertEqual(ch.catchup_days, 5)
        self.assertEqual(ch.catchup_source, "?timeshift=${start}&duration=${duration}")

    # -- 4. Backup & Restore (.novabackup) --------------------------------------
    def test_backup_and_restore_cycle(self):
        """Complete export and import cycle of .novabackup package."""
        # Seed test data
        prof = ProviderProfile(
            id="p1",
            name="Sports VIP",
            kind="xtream",
            server="http://vip-streams.net:8080",
            username="testuser",
            password="secretpassword",
        )
        self.profiles.save(prof)
        self.profiles.set_active("p1")

        self.favorites.add("http://vip-streams.net/live/101.ts")
        self.favorites.add("http://vip-streams.net/live/102.ts")

        self.history.record("http://vip-streams.net/live/101.ts", "Premier League HD")
        self.resume.save("http://vip-streams.net/movie/12.mp4", 1245.0, 7200.0)

        self.config.volume = 85
        self.config.hw_acceleration = "d3d11va"
        self.config.audio_boost = "dialogue"
        self.config.save()

        # Export backup
        backup_file = self.tmp / "test_export.novabackup"
        export_backup(
            backup_file,
            self.config,
            self.profiles,
            self.favorites,
            self.history,
            self.resume,
        )
        self.assertTrue(backup_file.exists())

        # Inspect json structure
        content = json.loads(backup_file.read_text(encoding="utf-8"))
        self.assertEqual(content["format"], "nova_iptv_backup")
        self.assertEqual(len(content["profiles"]), 1)
        self.assertEqual(content["config"]["hw_acceleration"], "d3d11va")
        self.assertEqual(content["config"]["audio_boost"], "dialogue")
        self.assertEqual(len(content["favorites"]), 2)

        # Create new fresh target stores
        new_tmp = self.tmp / "restored"
        new_tmp.mkdir()
        target_settings = QSettings(str(new_tmp / "cfg.ini"), QSettings.IniFormat)
        target_config = AppConfig(target_settings)
        target_profiles = ProfileStore(new_tmp / "prof.json")
        target_favs = FavoritesStore(new_tmp / "favs.json")
        target_hist = HistoryStore(new_tmp / "hist.json")
        target_res = ResumeStore(new_tmp / "res.json")

        # Import into fresh targets
        summary = import_backup(
            backup_file,
            target_config,
            target_profiles,
            target_favs,
            target_hist,
            target_res,
        )
        self.assertEqual(summary["profiles"], 1)
        self.assertEqual(summary["favorites"], 2)
        self.assertEqual(summary["history"], 1)
        self.assertEqual(summary["resume"], 1)

        # Verify restored values
        self.assertEqual(target_config.hw_acceleration, "d3d11va")
        self.assertEqual(target_config.audio_boost, "dialogue")
        self.assertEqual(target_config.volume, 85)
        self.assertIn("http://vip-streams.net/live/101.ts", target_favs.all())
        self.assertIsNotNone(target_profiles.get("p1"))
        self.assertEqual(target_profiles.get("p1").username, "testuser")

    # -- 5. Multi-View Sports Grid ---------------------------------------------
    def test_multiview_grid_layouts(self):
        """MultiViewGrid creates and manages quad, triple, and dual tile layouts."""
        grid = MultiViewGrid()
        self.assertEqual(len(grid.tiles), 4)
        self.assertEqual(grid.current_layout, "quad")

        # Layout switching
        grid.set_layout("dual")
        self.assertEqual(grid.current_layout, "dual")
        self.assertFalse(grid.tiles[0].isHidden())
        self.assertFalse(grid.tiles[1].isHidden())
        self.assertTrue(grid.tiles[2].isHidden())
        self.assertTrue(grid.tiles[3].isHidden())

        grid.set_layout("triple")
        self.assertEqual(grid.current_layout, "triple")
        self.assertFalse(grid.tiles[0].isHidden())
        self.assertFalse(grid.tiles[1].isHidden())
        self.assertFalse(grid.tiles[2].isHidden())
        self.assertTrue(grid.tiles[3].isHidden())

        grid.set_layout("quad")
        self.assertEqual(grid.current_layout, "quad")
        for tile in grid.tiles:
            self.assertFalse(tile.isHidden())

        grid.stop_all()

    def test_multiview_audio_focus(self):
        """Focusing audio on one MultiView tile mutes all other tiles."""
        grid = MultiViewGrid()
        # Set audio focus to tile 2
        grid.set_audio_focus(2)
        self.assertTrue(grid.tiles[2]._audio_active)
        self.assertFalse(grid.tiles[0]._audio_active)
        self.assertFalse(grid.tiles[1]._audio_active)
        self.assertFalse(grid.tiles[3]._audio_active)

        # Switch audio focus to tile 0
        grid.set_audio_focus(0)
        self.assertTrue(grid.tiles[0]._audio_active)
        self.assertFalse(grid.tiles[2]._audio_active)

        grid.stop_all()


if __name__ == "__main__":
    unittest.main()
