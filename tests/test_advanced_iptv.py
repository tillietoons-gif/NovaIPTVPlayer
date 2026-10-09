"""Unit tests for the advanced IPTV player UI/UX enhancements.

Tests the following components:
1. Player diagnostics media_info and playback speed scaling.
2. StreamStatsHud real-time diagnostics HUD.
3. VolumeToast floating volume HUD.
4. ChannelNumberOsd direct numeric tuning display.
5. QuickZapperOverlay sliding channel zapper drawer.
6. Grid sorting (Default, A-Z, Z-A, 4K UHD First).
7. Quality filter chips (All, Favorites, 4K UHD, FHD 1080p).
8. Sleep Timer scheduling, countdown, and playback shutdown.
9. ShortcutsDialog documentation of new shortcuts.
"""

import sys
import unittest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt

from app.player import Player
from app.models import Channel
from ui.widgets import (
    StreamStatsHud, VolumeToast, ChannelNumberOsd, QuickZapperOverlay, make_icon
)
from ui.dialogs import ShortcutsDialog
from ui.main_window import MainWindow

# Ensure single QApplication exists for GUI widget tests
_app = QApplication.instance() or QApplication(sys.argv)


class TestAdvancedIPTVPlayer(unittest.TestCase):

    def setUp(self):
        self.player = Player()

    def tearDown(self):
        self.player.stop()

    def test_player_media_info_structure(self):
        """Player.media_info returns a well-structured diagnostics dictionary."""
        info = self.player.media_info()
        self.assertIsInstance(info, dict)
        self.assertIn("video_codec", info)
        self.assertIn("audio_codec", info)
        self.assertIn("width", info)
        self.assertIn("height", info)
        self.assertIn("fps", info)
        self.assertIn("bitrate", info)
        self.assertIn("format", info)
        self.assertIn("frames_rendered", info)
        self.assertIn("frames_dropped", info)
        self.assertIn("playback_speed", info)
        self.assertEqual(info["playback_speed"], 1.0)

    def test_player_playback_speed_control(self):
        """Player.set_speed updates speed property and clamps safely."""
        self.assertEqual(self.player.speed, 1.0)
        self.player.set_speed(1.5)
        self.assertAlmostEqual(self.player.speed, 1.5, places=2)
        self.player.set_speed(2.0)
        self.assertAlmostEqual(self.player.speed, 2.0, places=2)
        self.player.set_speed(0.5)
        self.assertAlmostEqual(self.player.speed, 0.5, places=2)
        # Clamps to safe range [0.25, 4.0]
        self.player.set_speed(0.1)
        self.assertAlmostEqual(self.player.speed, 0.25, places=2)
        self.player.set_speed(10.0)
        self.assertAlmostEqual(self.player.speed, 4.0, places=2)

    def test_stream_stats_hud_display(self):
        """StreamStatsHud renders diagnostic metrics cleanly without errors."""
        hud = StreamStatsHud()
        hud.update_stats({
            "channel": "HBO HD",
            "video_codec": "h264",
            "audio_codec": "aac",
            "width": 1920,
            "height": 1080,
            "fps": 60.0,
            "bitrate": 6500000,
            "format": "hls",
            "frames_rendered": 1200,
            "frames_dropped": 2,
            "playback_speed": 1.0,
            "stream_url": "http://example.com/live/hbo.m3u8",
        })
        self.assertEqual(hud._rows["res"].text(), "1920 × 1080")
        self.assertIn("60.0 fps", hud._rows["fps"].text())
        self.assertEqual(hud._rows["vcodec"].text(), "H264")
        self.assertEqual(hud._rows["acodec"].text(), "AAC")
        self.assertIn("Mbps", hud._rows["bitrate"].text())
        self.assertEqual(hud._rows["fmt"].text(), "HLS")
        self.assertIn("1200", hud._rows["frames"].text())
        self.assertIn("2", hud._rows["frames"].text())

    def test_volume_toast_osd(self):
        """VolumeToast formats normal, boosted (>100%), and muted states."""
        toast = VolumeToast()
        toast.show_volume(75, muted=False)
        self.assertEqual(toast.text_lbl.text(), "75%")
        self.assertEqual(toast.bar.value(), 75)

        # Boosted volume
        toast.show_volume(120, muted=False)
        self.assertIn("120%", toast.text_lbl.text())
        self.assertIn("Boost", toast.text_lbl.text())

        # Muted
        toast.show_volume(50, muted=True)
        self.assertIn("Muted", toast.text_lbl.text())

    def test_channel_number_osd(self):
        """ChannelNumberOsd formats direct number tuning feedback."""
        osd = ChannelNumberOsd()
        osd.show_digits("12")
        self.assertEqual(osd.text(), "CH 12")
        self.assertFalse(osd.isHidden())

    def test_quick_zapper_filtering_and_selection(self):
        """QuickZapperOverlay displays channels, filters by text/category, and emits on selection."""
        ch1 = Channel(name="BBC One HD", url="http://ch1", group="UK")
        ch2 = Channel(name="Sky Cinema 4K", url="http://ch2", group="Cinema")
        ch3 = Channel(name="CNN International", url="http://ch3", group="News")

        zapper = QuickZapperOverlay()
        zapper.set_channels([ch1, ch2, ch3], current=ch1)
        self.assertEqual(zapper.list_widget.count(), 3)

        # Filter by search
        zapper.search_input.setText("Sky")
        self.assertEqual(zapper.list_widget.count(), 1)
        item = zapper.list_widget.item(0)
        self.assertIn("Sky Cinema", item.text())

        # Reset search & filter by category
        zapper.search_input.setText("")
        zapper.cat_box.setCurrentText("News")
        self.assertEqual(zapper.list_widget.count(), 1)
        self.assertIn("CNN", zapper.list_widget.item(0).text())

        # Channel selection emission
        selected_ch = []
        zapper.channel_selected.connect(lambda ch: selected_ch.append(ch))
        zapper._on_item_activated(zapper.list_widget.item(0))
        self.assertEqual(len(selected_ch), 1)
        self.assertEqual(selected_ch[0].name, "CNN International")

    def test_grid_sorting_and_quality_filters(self):
        """MainWindow._visible_channels properly sorts and filters channels."""
        win = MainWindow()
        win.channels = [
            Channel(name="Eurosport 1", url="http://c1", group="Sports"),
            Channel(name="Sky Sports 4K UHD", url="http://c2", group="Sports"),
            Channel(name="Animal Planet FHD", url="http://c3", group="Nature"),
            Channel(name="BBC News", url="http://c4", group="News"),
        ]
        win.favorites.add("http://c1")

        # 1. Quality filter: 4K UHD
        win._grid_quality_filter = "4k"
        vis = win._visible_channels()
        self.assertEqual(len(vis), 1)
        self.assertEqual(vis[0].name, "Sky Sports 4K UHD")

        # 2. Quality filter: FHD
        win._grid_quality_filter = "fhd"
        vis = win._visible_channels()
        self.assertEqual(len(vis), 1)
        self.assertEqual(vis[0].name, "Animal Planet FHD")

        # 3. Quality filter: Favorites
        win._grid_quality_filter = "favs"
        vis = win._visible_channels()
        self.assertEqual(len(vis), 1)
        self.assertEqual(vis[0].name, "Eurosport 1")

        # 4. Sorting: Name A-Z
        win._grid_quality_filter = "all"
        win._grid_sort_mode = "az"
        vis = win._visible_channels()
        self.assertEqual(vis[0].name, "Animal Planet FHD")
        self.assertEqual(vis[-1].name, "Sky Sports 4K UHD")

        # 5. Sorting: 4K First
        win._grid_sort_mode = "4k"
        vis = win._visible_channels()
        self.assertEqual(vis[0].name, "Sky Sports 4K UHD")
        self.assertEqual(vis[1].name, "Animal Planet FHD")

    def test_sleep_timer_logic(self):
        """MainWindow._set_sleep_timer schedules and counts down sleep timer."""
        win = MainWindow()
        win._set_sleep_timer(30)
        self.assertEqual(win._sleep_timer_minutes, 30)
        self.assertEqual(win._sleep_seconds_remaining, 1800)
        self.assertFalse(win.sleep_badge.isHidden())

        # Tick 1 second
        win._on_sleep_tick()
        self.assertEqual(win._sleep_seconds_remaining, 1799)

        # Disable sleep timer
        win._set_sleep_timer(0)
        self.assertEqual(win._sleep_timer_minutes, 0)
        self.assertEqual(win._sleep_seconds_remaining, 0)
        self.assertTrue(win.sleep_badge.isHidden())

    def test_shortcuts_dialog_content(self):
        """ShortcutsDialog includes documented keys for Zapper, Stats, Sleep, and 0-9."""
        dlg = ShortcutsDialog()
        labels = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        self.assertIn("Z / Enter", labels)
        self.assertIn("I", labels)
        self.assertIn("T", labels)
        self.assertIn("0–9", labels)


if __name__ == "__main__":
    unittest.main()
