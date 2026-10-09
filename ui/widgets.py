"""Reusable widgets: async logo loading, channel cards/grid, EPG timeline."""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from PySide6.QtCore import Qt, Signal, QRunnable, QThreadPool, QObject, Slot
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QWidget, QLineEdit, QSizePolicy,
)

from app.models import Channel, EPGProgram


# -- async image loading ----------------------------------------------------

class _ImageSignals(QObject):
    done = Signal(QImage)


class _ImageLoader(QRunnable):
    """Fetch a logo off-thread so scrolling never blocks on the network."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.signals = _ImageSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # runs in a worker thread
        try:
            resp = requests.get(self.url, timeout=8,
                                headers={"User-Agent": "NovaIPTV/1.0"})
            resp.raise_for_status()
            img = QImage.fromData(resp.content)
            if not img.isNull():
                self.signals.done.emit(img)
        except Exception:
            pass  # keep the placeholder


class LogoLabel(QLabel):
    """QLabel that loads a remote logo asynchronously with a placeholder."""

    _pool = QThreadPool.globalInstance()

    def __init__(self, size: int = 56, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setText("📺")
        self.setStyleSheet(
            "background:#0b0e14; border-radius:8px; font-size:22px;"
        )
        self._loader: _ImageLoader | None = None

    def load(self, url: str) -> None:
        self.setText("📺")
        self.setPixmap(QPixmap())
        if not url:
            return
        self._loader = _ImageLoader(url)
        self._loader.signals.done.connect(self._on_image)
        self._pool.start(self._loader)

    def _on_image(self, img: QImage) -> None:
        pix = QPixmap.fromImage(img).scaled(
            self._size, self._size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(pix)


# -- channel card / grid -----------------------------------------------------

class ChannelCard(QFrame):
    clicked = Signal(object)          # Channel
    fav_toggled = Signal(object, bool)  # Channel, new_state

    def __init__(self, channel: Channel, is_fav: bool = False,
                 epg_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.channel = channel
        self.setObjectName("channelCard")
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        self.logo = LogoLabel(52)
        self.logo.load(channel.logo)
        lay.addWidget(self.logo)

        text = QVBoxLayout()
        name = QLabel(channel.name)
        name.setObjectName("cardName")
        name.setWordWrap(True)
        text.addWidget(name)
        meta = QLabel(epg_text or channel.display_group)
        meta.setObjectName("cardMeta")
        meta.setWordWrap(True)
        text.addWidget(meta)
        lay.addLayout(text, 1)

        self.fav_btn = QPushButton("★" if is_fav else "☆")
        self.fav_btn.setObjectName("favBtn")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setChecked(is_fav)
        self.fav_btn.setFixedWidth(34)
        self.fav_btn.setToolTip("Toggle favorite")
        self.fav_btn.clicked.connect(self._on_fav)
        lay.addWidget(self.fav_btn)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.channel)
        super().mousePressEvent(event)

    def _on_fav(self, checked: bool) -> None:
        self.fav_btn.setText("★" if checked else "☆")
        self.fav_toggled.emit(self.channel, checked)

    def set_favorite(self, fav: bool) -> None:
        self.fav_btn.setChecked(fav)
        self.fav_btn.setText("★" if fav else "☆")


class ChannelGrid(QWidget):
    """Scrollable responsive grid of ChannelCards."""

    channel_chosen = Signal(object)
    fav_toggled = Signal(object, bool)

    def __init__(self, parent=None, columns: int = 3) -> None:
        super().__init__(parent)
        self._columns = columns
        self._cards: list[ChannelCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self._inner)

        self._empty = QLabel("No channels. Load a playlist to get started.")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet("color:#8b95a9; font-size:14px; padding:40px;")

    def set_channels(self, channels: list[Channel],
                     favorites: set[str],
                     epg_lookup=None) -> None:
        # Clear old cards.
        for card in self._cards:
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        if not channels:
            self._grid.addWidget(self._empty, 0, 0)
            return
        self._empty.setParent(None)

        for i, ch in enumerate(channels):
            epg_text = ""
            if epg_lookup is not None:
                try:
                    epg_text = epg_lookup(ch) or ""
                except Exception:
                    epg_text = ""
            card = ChannelCard(ch, ch.url in favorites, epg_text)
            card.clicked.connect(self.channel_chosen.emit)
            card.fav_toggled.connect(self.fav_toggled.emit)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._grid.addWidget(card, i // self._columns, i % self._columns)
            self._cards.append(card)

    def update_favorite(self, channel_url: str, fav: bool) -> None:
        for card in self._cards:
            if card.channel.url == channel_url:
                card.set_favorite(fav)


# -- search -------------------------------------------------------------------

class SearchBar(QLineEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.setPlaceholderText("🔍  Search channels…")
        self.setClearButtonEnabled(True)


# -- video display ---------------------------------------------------------------

class VideoWidget(QWidget):
    """Displays decoded video frames from the player engine.

    Frames arrive via the ``set_frame`` slot (emitted from the decode
    thread -- Qt queues the call into the GUI thread automatically).
    Each frame is painted aspect-fit and centered on a black background;
    before the first frame (or after ``clear()``) a "No signal"
    placeholder is shown instead.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("videoFrame")
        self.setMinimumHeight(300)
        self._pixmap: QPixmap | None = None

    @Slot(QImage)
    def set_frame(self, img: QImage) -> None:
        if img.isNull():
            return
        self._pixmap = QPixmap.fromImage(img)
        self.update()  # schedule a repaint in the GUI thread

    def clear(self) -> None:
        """Forget the last frame and show the placeholder again."""
        self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor("#8b95a9"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No signal")


# -- EPG timeline ---------------------------------------------------------------

class EpgTimelineWidget(QWidget):
    """Simple horizontal guide: one row per channel with programme blocks."""

    channel_chosen = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self._layout.addWidget(self.scroll)
        self._inner = QWidget()
        self._rows = QVBoxLayout(self._inner)
        self._rows.setSpacing(6)
        self.scroll.setWidget(self._inner)

    def set_guide(self, items: list[tuple[Channel, list[EPGProgram]]],
                  hours: int = 6) -> None:
        # Clear.
        while self._rows.count():
            child = self._rows.takeAt(0).widget()
            if child:
                child.deleteLater()
        if not items:
            lbl = QLabel("Load an XMLTV guide to see the programme timeline.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#8b95a9; padding:40px;")
            self._rows.addWidget(lbl)
            return

        now = datetime.now(timezone.utc)
        for ch, progs in items:
            row = QFrame()
            row.setObjectName("channelCard")
            hl = QHBoxLayout(row)
            name = QLabel(ch.name)
            name.setFixedWidth(180)
            name.setWordWrap(True)
            hl.addWidget(name)
            blocks = QHBoxLayout()
            blocks.setSpacing(4)
            shown = 0
            for pr in progs:
                if shown >= 4:
                    break
                is_now = pr.start <= now < pr.stop
                mins = max(1, int((pr.stop - pr.start).total_seconds() // 60))
                lbl = QLabel(
                    f"{'▶ ' if is_now else ''}{pr.title}\n"
                    f"{pr.start.strftime('%H:%M')}–{pr.stop.strftime('%H:%M')} ({mins}m)"
                )
                lbl.setWordWrap(True)
                lbl.setStyleSheet(
                    "background:rgba(0,212,255,0.12); border:1px solid rgba(0,212,255,0.35);"
                    "border-radius:8px; padding:6px 8px; font-size:11px;"
                    if is_now else
                    "background:#161c27; border:1px solid #232c3d;"
                    "border-radius:8px; padding:6px 8px; font-size:11px;"
                )
                lbl.setMinimumWidth(150)
                blocks.addWidget(lbl)
                shown += 1
            if shown == 0:
                none = QLabel("No programme data")
                none.setStyleSheet("color:#8b95a9; font-size:11px;")
                blocks.addWidget(none)
            blocks.addStretch(1)
            hl.addLayout(blocks, 1)
            play = QPushButton("▶ Play")
            play.setObjectName("ctlBtn")
            play.clicked.connect(lambda _=False, c=ch: self.channel_chosen.emit(c))
            hl.addWidget(play)
            self._rows.addWidget(row)
        self._rows.addStretch(1)
