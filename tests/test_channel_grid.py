from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.models import Channel
from ui.widgets import ChannelGrid


class TestChannelGrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_large_playlist_renders_incrementally(self) -> None:
        grid = ChannelGrid()
        channels = [
            Channel(name=f"Channel {index}", url=f"https://example.test/{index}")
            for index in range(121)
        ]

        grid.set_channels(channels, set())
        self.assertEqual(len(grid._cards), grid.PAGE_SIZE)
        self.assertIsNotNone(grid._load_more_button)

        grid._load_more_button.click()
        self.assertEqual(len(grid._cards), grid.PAGE_SIZE * 2)
        self.assertIsNotNone(grid._load_more_button)

        grid._load_more_button.click()
        self.assertEqual(len(grid._cards), len(channels))
        self.assertIsNone(grid._load_more_button)
        grid.deleteLater()


if __name__ == "__main__":
    unittest.main()
