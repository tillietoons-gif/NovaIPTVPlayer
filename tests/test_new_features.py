from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.external_player import detect_players, launch_player
from app.models import Channel
from app.player import Player
from app.xtream import XtreamClient
from ui.main_window import _AutoPlayNextBanner, _PipWindow
from ui.theme import build_stylesheet, COLORS
from ui.widgets import VideoWidget, make_icon, AudioVisualizer, HeroCard, quality_of



class TestNewFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_aspect_ratio_and_subtitles_on_video_widget(self) -> None:
        widget = VideoWidget()
        self.assertEqual(widget.aspect_ratio(), "auto")

        for mode in ("16:9", "4:3", "fill", "auto"):
            widget.set_aspect_ratio(mode)
            self.assertEqual(widget.aspect_ratio(), mode)

        widget.set_subtitle("This is a live subtitle test")
        self.assertEqual(widget._subtitle_text, "This is a live subtitle test")

        # Paint with dummy frame
        img = QImage(320, 240, QImage.Format_RGB888)
        img.fill(Qt.blue)
        widget.set_frame(img)
        widget.resize(640, 480)

        # Ensure paint event executes cleanly with aspect ratio and subtitle overlay
        pm = widget.grab()
        self.assertFalse(pm.isNull())
        self.assertEqual(pm.width(), 640)
        self.assertEqual(pm.height(), 480)

    def test_player_tracks_api(self) -> None:
        player = Player()
        self.assertEqual(player.audio_tracks(), [])
        self.assertEqual(player.subtitle_tracks(), [])
        self.assertEqual(player.current_audio_track, 0)
        self.assertEqual(player.current_subtitle_track, -1)

        # Simulate worker discovering tracks
        sample_audio = [{"index": 1, "language": "eng", "title": "English", "codec": "aac"}]
        sample_subs = [{"index": 2, "language": "spa", "title": "Spanish"}]
        player._on_tracks_ready(sample_audio, sample_subs)

        self.assertEqual(len(player.audio_tracks()), 1)
        self.assertEqual(len(player.subtitle_tracks()), 1)
        self.assertEqual(player.current_audio_track, 1)

        player.set_audio_track(1)
        self.assertEqual(player.current_audio_track, 1)

        player.set_subtitle_track(2)
        self.assertEqual(player.current_subtitle_track, 2)

        player.set_subtitle_track(-1)
        self.assertEqual(player.current_subtitle_track, -1)

    def test_external_player_detection_and_launch(self) -> None:
        players = detect_players()
        self.assertIsInstance(players, dict)

        # Empty url should return failure
        ok, msg = launch_player("", "Test Channel")
        self.assertFalse(ok)
        self.assertIn("empty", msg.lower())

        # Test launch fallback behavior with dummy player
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            with patch("app.external_player.detect_players", return_value={"VLC": "vlc.exe"}):
                ok, msg = launch_player("http://example.com/stream.m3u8", "Test Channel", "vlc")
                self.assertTrue(ok)
                self.assertIn("VLC", msg)
                mock_popen.assert_called_once()

    def test_pip_window_creation_and_events(self) -> None:
        class DummyMain:
            def __init__(self):
                self._current_channel = Channel(name="Test News", url="http://test/stream.m3u8", kind="live")
                self.thumb_video = VideoWidget()
                self.player = Player()
            def _toggle_pause(self):
                pass
            def _toggle_fullscreen(self):
                pass

        main = DummyMain()
        pip = _PipWindow(main)
        self.assertTrue(bool(pip.windowFlags() & Qt.WindowStaysOnTopHint))
        self.assertTrue(bool(pip.windowFlags() & Qt.FramelessWindowHint))
        self.assertEqual(pip.title_lbl.text(), "Test News")
        self.assertIsNotNone(pip.video)

        # Test state change update
        pip._on_player_state("playing")
        pip._on_player_state("paused")

        pip.close()

    def test_auto_play_next_banner(self) -> None:
        next_ep = Channel(name="Chapter Two", url="http://test/ep2.mp4", kind="series", season="1", episode_num="2")
        banner = _AutoPlayNextBanner(next_ep, countdown_sec=3)
        self.assertIn("S01E02", banner.title_lbl.text())
        self.assertIn("Chapter Two", banner.title_lbl.text())

        play_clicked = False
        def on_play():
            nonlocal play_clicked
            play_clicked = True

        banner.play_now_clicked.connect(on_play)
        banner.play_btn.click()
        self.assertTrue(play_clicked)
        banner.stop()

    def test_xtream_timeshift_url_and_guide_support(self) -> None:
        client = XtreamClient("http://myiptv.com:8080", "user123", "pass456")
        start_time = datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)
        url = client.timeshift_url(789, start_time, duration_minutes=45)

        self.assertIn("timeshift/user123/pass456/45/2026-10-09:14-30/789.ts", url)

    def test_new_icons_registered(self) -> None:
        for icon_name in ("aspect", "pip", "subtitle", "cc", "calendar", "epg", "external", "launch"):
            icon = make_icon(icon_name, 24, "white")
            self.assertFalse(icon.isNull())

    def test_audio_visualizer_widget(self) -> None:
        vis = AudioVisualizer(bar_count=4)
        self.assertFalse(vis._active)
        vis.set_active(True)
        self.assertTrue(vis._active)
        vis._tick()
        # Ensure grab executes paintEvent cleanly
        pm = vis.grab()
        self.assertFalse(pm.isNull())
        vis.stop()
        self.assertFalse(vis._active)

    def test_quality_of_classification(self) -> None:
        ch_4k = Channel(name="Sky Sports UHD 4K", url="http://test/4k")
        ch_fhd = Channel(name="BBC One FHD 1080p", url="http://test/fhd")
        ch_hd = Channel(name="Discovery Channel", url="http://test/hd")
        self.assertEqual(quality_of(ch_4k), "4K")
        self.assertEqual(quality_of(ch_fhd), "FHD")
        self.assertEqual(quality_of(ch_hd), "HD")

    def test_hero_card_tags_and_feature(self) -> None:
        hero = HeroCard()
        hero.set_feature(None)
        self.assertFalse(hero.watch_btn.isEnabled())

        ch = Channel(name="Canal+ 4K Cinema", url="http://test/canal", kind="live", group="Movies")

        hero.set_feature(ch)
        self.assertTrue(hero.watch_btn.isEnabled())
        self.assertFalse(hero.quality_tag.isHidden())

        self.assertIn("4K ULTRA HD", hero.quality_tag.text())
        self.assertEqual(hero.title.text(), "Canal+ 4K Cinema")

    def test_luxury_theme_tokens_and_stylesheet(self) -> None:
        self.assertIn("card_hover", COLORS)
        self.assertIn("cyan", COLORS)
        qss = build_stylesheet()
        self.assertIn("#090b10", qss)
        self.assertIn("#8b5cf6", qss)
        self.assertIn("channelCard", qss)

