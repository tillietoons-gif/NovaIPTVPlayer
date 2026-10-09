from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.epg import EPGManager
from app.player import _open_options
from app.playlist import categories, filter_channels, parse_m3u


class TestPlaylistParsing(unittest.TestCase):
    def test_parse_m3u_extracts_channels_and_kind_tags(self) -> None:
        text = '''#EXTM3U
#EXTINF:-1 tvg-id="chan1" tvg-logo="https://example.com/logo1.png" group-title="News",BBC News
https://example.com/live
#EXTINF:-1 tvg-id="movie1" group-title="Movies",Movie 1
https://example.com/movie
#EXTINF:-1 tvg-id="series1" group-title="Series",Series 1
https://example.com/series
'''

        channels = parse_m3u(text)

        self.assertEqual([c.name for c in channels], ["BBC News", "Movie 1", "Series 1"])
        self.assertEqual([c.kind for c in channels], ["live", "movie", "series"])
        self.assertEqual(categories(channels), ["Movies", "News", "Series"])

        movie_channels = filter_channels(channels, kind="movie")
        self.assertEqual(len(movie_channels), 1)
        self.assertEqual(movie_channels[0].name, "Movie 1")


class TestEPGParsing(unittest.TestCase):
    def test_load_epg_and_now_next(self) -> None:
        tvxml = '''<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="chan1">
    <display-name>BBC One</display-name>
  </channel>
  <programme start="20240102100000 +0000" stop="20240102120000 +0000" channel="chan1">
    <title>Morning Show</title>
  </programme>
  <programme start="20240102120000 +0000" stop="20240102130000 +0000" channel="chan1">
    <title>Lunch News</title>
  </programme>
</tv>
'''

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "guide.xml"
            path.write_text(tvxml, encoding="utf-8")

            manager = EPGManager()
            count = manager.load(str(path))

            self.assertEqual(count, 2)
            now = datetime(2024, 1, 2, 11, 30, tzinfo=timezone.utc)
            current, nxt = manager.now_and_next("chan1", now=now)

            self.assertIsNotNone(current)
            self.assertEqual(current.title, "Morning Show")
            self.assertIsNotNone(nxt)
            self.assertEqual(nxt.title, "Lunch News")

    def test_load_epg_rejects_invalid_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.xml"
            path.write_text("<tv><broken>", encoding="utf-8")

            manager = EPGManager()
            with self.assertRaises(ValueError):
                manager.load(str(path))


class TestInputValidation(unittest.TestCase):
    def test_parse_m3u_ignores_blank_and_malformed_entries(self) -> None:
        text = '''#EXTM3U
#EXTINF:-1 tvg-id="chan1" group-title="News",BBC News
https://example.com/live

#EXTINF:-1, Broken Entry Without Url
#EXTINF:bad
not-a-url
'''

        channels = parse_m3u(text)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0].name, "BBC News")

    def test_http_player_options_include_playlist_headers_and_reconnect(self) -> None:
        options = _open_options(
            "https://example.com/live",
            {"User-Agent": "VLC Player", "Referer": "https://provider.example/"},
        )

        self.assertEqual(options["user_agent"], "VLC Player")
        self.assertEqual(options["referer"], "https://provider.example/")
        self.assertEqual(options["reconnect"], "1")
        self.assertEqual(options["reconnect_streamed"], "1")
        self.assertEqual(options["reconnect_delay_max"], "5")

    def test_non_http_player_options_do_not_include_http_settings(self) -> None:
        options = _open_options("rtsp://example.com/live", {})

        self.assertEqual(options, {"rw_timeout": "15000000"})

    def test_parse_m3u_preserves_stream_http_headers(self) -> None:
        text = '''#EXTM3U
#EXTINF:-1,Channel with headers
#EXTVLCOPT:http-user-agent=VLC Player
#EXTVLCOPT:http-referrer=https://provider.example/
https://example.com/live
#EXTINF:-1,Channel without headers
https://example.com/other
'''

        channels = parse_m3u(text)

        self.assertEqual(
            channels[0].stream_headers,
            {
                "User-Agent": "VLC Player",
                "Referer": "https://provider.example/",
            },
        )
        self.assertEqual(channels[1].stream_headers, {})


if __name__ == "__main__":
    unittest.main()
