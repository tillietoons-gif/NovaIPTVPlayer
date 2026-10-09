"""Reusable widgets for the Nova IPTV dashboard.

All icons are drawn with QPainter (no image files, no emojis).
"""

from __future__ import annotations

import hashlib
import math

import requests
from PySide6.QtCore import (
    Qt, Signal, Slot, QRunnable, QThreadPool, QObject,
    QPointF, QRectF, QSize,
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QIcon, QPen, QLinearGradient,
    QFont, QPainterPath,
)
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QWidget, QLineEdit, QSizePolicy,
    QProgressBar,
)

from app.models import Channel, EPGProgram
from ui.theme import COLORS


# -- drawn icons ---------------------------------------------------------------

def make_icon(name: str, size: int = 20,
              color: str = COLORS["text"]) -> QIcon:
    """Draw a simple vector icon and return it as QIcon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    col = QColor(color)
    lw = max(2, size // 11)
    pen = QPen(col, lw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = float(size)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(s * x1, s * y1), QPointF(s * x2, s * y2))

    if name == "play":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon([
            QPointF(s * 0.36, s * 0.26), QPointF(s * 0.36, s * 0.74),
            QPointF(s * 0.72, s * 0.50),
        ])
    elif name == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        w = s * 0.17
        p.drawRoundedRect(QRectF(s * 0.30, s * 0.26, w, s * 0.48), 2, 2)
        p.drawRoundedRect(QRectF(s * 0.53, s * 0.26, w, s * 0.48), 2, 2)
    elif name == "stop":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44), 2, 2)
    elif name == "prev":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(s * 0.24, s * 0.28, s * 0.12, s * 0.44))
        p.drawPolygon([
            QPointF(s * 0.68, s * 0.28), QPointF(s * 0.68, s * 0.72),
            QPointF(s * 0.36, s * 0.50),
        ])
    elif name == "next":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(s * 0.64, s * 0.28, s * 0.12, s * 0.44))
        p.drawPolygon([
            QPointF(s * 0.32, s * 0.28), QPointF(s * 0.32, s * 0.72),
            QPointF(s * 0.64, s * 0.50),
        ])
    elif name == "home":
        path = QPainterPath()
        path.moveTo(s * 0.18, s * 0.52)
        path.lineTo(s * 0.50, s * 0.22)
        path.lineTo(s * 0.82, s * 0.52)
        p.drawPath(path)
        p.drawRect(QRectF(s * 0.30, s * 0.50, s * 0.40, s * 0.30))
    elif name == "tv":
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.24, s * 0.68, s * 0.44), 4, 4)
        line(0.40, 0.68, 0.60, 0.68)
        line(0.50, 0.68, 0.50, 0.80)
        line(0.38, 0.80, 0.62, 0.80)
    elif name == "film":
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.52), 4, 4)
        line(0.36, 0.24, 0.36, 0.76)
        line(0.64, 0.24, 0.64, 0.76)
    elif name == "layers":
        for i, y in enumerate((0.28, 0.44, 0.60)):
            p.drawPolygon([
                QPointF(s * 0.50, s * (y - 0.10)),
                QPointF(s * 0.80, s * y),
                QPointF(s * 0.50, s * (y + 0.10)),
                QPointF(s * 0.20, s * y),
            ])
    elif name == "history":
        p.drawEllipse(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60))
        line(0.50, 0.50, 0.50, 0.32)
        line(0.50, 0.50, 0.64, 0.56)
    elif name == "replay":
        p.drawArc(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56),
                  40 * 16, 280 * 16)
        ang = math.radians(40.0)
        ex, ey = s * 0.5 + s * 0.28 * math.cos(ang), s * 0.5 - s * 0.28 * math.sin(ang)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon([
            QPointF(ex, ey),
            QPointF(ex - s * 0.16, ey - s * 0.03),
            QPointF(ex - s * 0.03, ey + s * 0.15),
        ])
    elif name == "list":
        for y in (0.30, 0.50, 0.70):
            line(0.30, y, 0.80, y)
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        for y in (0.30, 0.50, 0.70):
            p.drawEllipse(QRectF(s * 0.16, s * (y - 0.035), s * 0.07, s * 0.07))
    elif name == "star":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        pts = []
        for i in range(10):
            r = s * 0.36 if i % 2 == 0 else s * 0.15
            a = -math.pi / 2 + i * math.pi / 5
            pts.append(QPointF(s * 0.5 + r * math.cos(a),
                               s * 0.5 + r * math.sin(a)))
        p.drawPolygon(pts)
    elif name == "star_outline":
        pts = []
        for i in range(10):
            r = s * 0.36 if i % 2 == 0 else s * 0.15
            a = -math.pi / 2 + i * math.pi / 5
            pts.append(QPointF(s * 0.5 + r * math.cos(a),
                               s * 0.5 + r * math.sin(a)))
        p.drawPolygon(pts)
    elif name == "bell":
        p.drawArc(QRectF(s * 0.28, s * 0.18, s * 0.44, s * 0.50), 0, 180 * 16)
        p.drawRect(QRectF(s * 0.28, s * 0.42, s * 0.44, s * 0.18))
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(s * 0.44, s * 0.66, s * 0.12, s * 0.12))
    elif name == "gear":
        p.drawEllipse(QRectF(s * 0.32, s * 0.32, s * 0.36, s * 0.36))
        for i in range(8):
            a = i * math.pi / 4
            x1, y1 = 0.5 + 0.22 * math.cos(a), 0.5 + 0.22 * math.sin(a)
            x2, y2 = 0.5 + 0.34 * math.cos(a), 0.5 + 0.34 * math.sin(a)
            line(x1, y1, x2, y2)
    elif name == "search":
        p.drawEllipse(QRectF(s * 0.22, s * 0.22, s * 0.42, s * 0.42))
        line(0.58, 0.58, 0.80, 0.80)
    elif name == "close":
        line(0.28, 0.28, 0.72, 0.72)
        line(0.72, 0.28, 0.28, 0.72)
    elif name == "minus":
        line(0.28, 0.50, 0.72, 0.50)
    elif name == "maximize":
        p.drawRect(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44))
    elif name == "restore":
        p.drawRect(QRectF(s * 0.36, s * 0.24, s * 0.40, s * 0.40))
        p.drawRect(QRectF(s * 0.24, s * 0.36, s * 0.40, s * 0.40))
    elif name == "chevron_right":
        p.drawPolyline([QPointF(s * 0.38, s * 0.26),
                        QPointF(s * 0.62, s * 0.50),
                        QPointF(s * 0.38, s * 0.74)])
    elif name == "plus":
        line(0.50, 0.26, 0.50, 0.74)
        line(0.26, 0.50, 0.74, 0.50)
    elif name == "signal":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        for i, h in enumerate((0.20, 0.34, 0.48, 0.62)):
            x = s * (0.22 + i * 0.16)
            p.drawRoundedRect(QRectF(x, s * (0.78 - h), s * 0.10, s * h), 2, 2)
    elif name == "folder":
        p.drawRect(QRectF(s * 0.20, s * 0.30, s * 0.60, s * 0.44))
        line(0.20, 0.30, 0.20, 0.22)
        line(0.20, 0.22, 0.44, 0.22)
        line(0.44, 0.22, 0.50, 0.30)
    elif name == "expand":
        line(0.30, 0.70, 0.30, 0.30)
        line(0.30, 0.30, 0.70, 0.30)
        p.drawPolyline([QPointF(s * 0.30, s * 0.48),
                        QPointF(s * 0.48, s * 0.30),
                        QPointF(s * 0.66, s * 0.30)])
        p.drawPolyline([QPointF(s * 0.52, s * 0.70),
                        QPointF(s * 0.70, s * 0.70),
                        QPointF(s * 0.70, s * 0.52)])
    p.end()
    return QIcon(pm)


def brand_pixmap(size: int = 36) -> QPixmap:
    """Violet rounded square with a white play triangle (app logo mark)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(COLORS["accent"]))
    grad.setColorAt(1, QColor(COLORS["accent2"]))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    p.setBrush(QColor("white"))
    s = float(size)
    p.drawPolygon([
        QPointF(s * 0.38, s * 0.30), QPointF(s * 0.38, s * 0.70),
        QPointF(s * 0.68, s * 0.50),
    ])
    p.end()
    return pm


def avatar_pixmap(name: str, size: int = 36) -> QPixmap:
    """Colored circle with the user's initial."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    digest = hashlib.md5(name.encode()).hexdigest()
    hue = int(digest[:2], 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor.fromHsv(hue, 140, 200))
    p.drawEllipse(QRectF(0, 0, size, size))
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", max(10, size // 2 - 2))
    f.setBold(True)
    p.setFont(f)
    initial = (name.strip()[:1] or "?").upper()
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, initial)
    p.end()
    return pm


def poster_pixmap(width: int, height: int, title: str,
                  seed: str = "") -> QPixmap:
    """Honest placeholder art: dark gradient + title text (no fake posters)."""
    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    digest = hashlib.md5((seed or title).encode()).hexdigest()
    hue = int(digest[:2], 16) % 360
    grad = QLinearGradient(0, 0, width, height)
    grad.setColorAt(0, QColor.fromHsv(hue, 120, 70))
    grad.setColorAt(1, QColor(COLORS["surface"]))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0, 0, width, height), 12, 12)
    # soft play glyph watermark
    p.setPen(QColor(255, 255, 255, 40))
    p.setBrush(QColor(255, 255, 255, 30))
    s = min(width, height) * 0.28
    cx, cy = width / 2, height / 2 - 10
    p.drawPolygon([
        QPointF(cx - s * 0.35, cy - s * 0.45),
        QPointF(cx - s * 0.35, cy + s * 0.45),
        QPointF(cx + s * 0.45, cy),
    ])
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 11)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(10, height - 52, width - 20, 44),
               Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, title)
    p.end()
    return pm


def quality_of(channel: Channel) -> str:
    n = channel.name.lower()
    if "4k" in n or "uhd" in n:
        return "4K"
    return "HD"


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


def _placeholder_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(COLORS["surface"]))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(COLORS["muted"]))
    s = float(size)
    p.drawPolygon([
        QPointF(s * 0.38, s * 0.32), QPointF(s * 0.38, s * 0.68),
        QPointF(s * 0.66, s * 0.50),
    ])
    p.end()
    return pm


class LogoLabel(QLabel):
    """QLabel that loads a remote logo asynchronously with a placeholder."""

    _pool = QThreadPool.globalInstance()

    def __init__(self, size: int = 56, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(_placeholder_pixmap(size))
        self._loader: _ImageLoader | None = None

    def load(self, url: str) -> None:
        self.setPixmap(_placeholder_pixmap(self._size))
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
        self.setPixmap(pix)


# -- small building blocks ----------------------------------------------------

class NavButton(QPushButton):
    def __init__(self, icon_name: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("navBtn")
        self.setCheckable(True)
        self.setIcon(make_icon(icon_name, 20))
        self.setIconSize(QSize(20, 20))
        self.setText(f"  {text}")
        self.setCursor(Qt.PointingHandCursor)


class IconButton(QPushButton):
    """Square icon button, optionally with a red notification dot."""

    def __init__(self, icon_name: str, size: int = 20, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("iconBtn")
        self.setIcon(make_icon(icon_name, size))
        self.setCursor(Qt.PointingHandCursor)
        self._dot = QLabel(self)
        self._dot.setFixedSize(9, 9)
        self._dot.setStyleSheet(
            "background:#ef4444; border-radius:4px; border:1px solid #0b0d13;")
        self._dot.hide()
        self._dot.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._dot.move(self.width() - 11, 4)

    def set_dot(self, visible: bool) -> None:
        self._dot.setVisible(visible)


class WinButton(QPushButton):
    def __init__(self, icon_name: str, parent=None, danger: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("winBtn")
        if danger:
            self.setProperty("danger", "true")
        self.setIcon(make_icon(icon_name, 14, COLORS["muted"]))
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 32)


class SectionHeader(QWidget):
    view_all = Signal()

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        lay.addWidget(t)
        lay.addStretch(1)
        btn = QPushButton("View All")
        btn.setObjectName("viewAllBtn")
        btn.setIcon(make_icon("chevron_right", 16, COLORS["accent"]))
        btn.setLayoutDirection(Qt.RightToLeft)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.view_all.emit)
        lay.addWidget(btn)


class StatPill(QLabel):
    """Connection status pill: green dot LIVE CONNECTED / grey OFFLINE."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("connPill")
        self.set_connected(False)

    def set_connected(self, ok: bool) -> None:
        dot = COLORS["green"] if ok else COLORS["muted"]
        text = "LIVE CONNECTED" if ok else "OFFLINE"
        self.setText(
            f'<span style="color:{dot}; font-size:12px;">●</span>'
            f'&nbsp;&nbsp;{text}'
        )


class SearchBar(QLineEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.setPlaceholderText("Search channels, movies, series...")
        self.setClearButtonEnabled(True)


# -- video display ---------------------------------------------------------------

class VideoWidget(QWidget):
    """Displays decoded video frames from the player engine.

    Frames arrive via the ``set_frame`` slot (emitted from the decode
    thread -- Qt queues the call into the GUI thread automatically).
    Each frame is painted aspect-fit and centered on a black background;
    before the first frame (or after ``clear()``) a placeholder is shown.
    """

    def __init__(self, parent=None, placeholder: str = "No signal") -> None:
        super().__init__(parent)
        self.setObjectName("videoFrame")
        self._pixmap: QPixmap | None = None
        self._placeholder = placeholder

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
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)


# -- channel card / grid -----------------------------------------------------

class _LogoArea(QWidget):
    """Logo with LIVE / quality badges overlaid (top-left / top-right)."""

    def __init__(self, channel: Channel, logo_size: int = 64,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("logoWrap")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.logo = LogoLabel(logo_size)
        self.logo.load(channel.logo)
        lay.addWidget(self.logo, alignment=Qt.AlignCenter)

        self.live_badge = QLabel('<span style="font-size:9px;">●</span> LIVE', self)
        self.live_badge.setObjectName("liveBadge")
        self.live_badge.setVisible(channel.kind == "live")

        self.quality_badge = QLabel(quality_of(channel), self)
        self.quality_badge.setObjectName("qualityBadge")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.live_badge.adjustSize()
        self.live_badge.move(6, 6)
        self.quality_badge.adjustSize()
        self.quality_badge.move(
            self.width() - self.quality_badge.width() - 6, 6)


class ChannelCard(QFrame):
    clicked = Signal(object)            # Channel
    fav_toggled = Signal(object, bool)  # Channel, new_state

    def __init__(self, channel: Channel, is_fav: bool = False,
                 epg_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.channel = channel
        self.setObjectName("channelCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(172)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.area = _LogoArea(channel)
        self.area.setFixedHeight(112)
        lay.addWidget(self.area)

        name = QLabel(channel.name)
        name.setObjectName("cardName")
        name.setWordWrap(True)
        name.setMaximumHeight(40)
        lay.addWidget(name)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        meta = QLabel(epg_text or channel.display_group)
        meta.setObjectName("cardMeta")
        meta.setWordWrap(True)
        bottom.addWidget(meta, 1)

        self.fav_btn = QPushButton()
        self.fav_btn.setObjectName("favBtn")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setChecked(is_fav)
        self.fav_btn.setIcon(make_icon(
            "star", 18, COLORS["accent"] if is_fav else COLORS["muted"]))
        self.fav_btn.setToolTip("Toggle favorite")
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.clicked.connect(self._on_fav)
        bottom.addWidget(self.fav_btn)
        lay.addLayout(bottom)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.channel)
        super().mousePressEvent(event)

    def _on_fav(self, checked: bool) -> None:
        self.fav_btn.setIcon(make_icon(
            "star" if checked else "star_outline", 18,
            COLORS["accent"] if checked else COLORS["muted"]))
        self.fav_toggled.emit(self.channel, checked)

    def set_favorite(self, fav: bool) -> None:
        self.fav_btn.setChecked(fav)
        self.fav_btn.setIcon(make_icon(
            "star" if fav else "star_outline", 18,
            COLORS["accent"] if fav else COLORS["muted"]))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class ChannelGrid(QWidget):
    """Scrollable responsive grid of ChannelCards."""

    channel_chosen = Signal(object)
    fav_toggled = Signal(object, bool)

    def __init__(self, parent=None, columns: int = 4) -> None:
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
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self._inner)

        self._empty = QLabel("No channels. Load a playlist to get started.")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet(
            f"color:{COLORS['muted']}; font-size:14px; padding:40px;")

    def set_channels(self, channels: list[Channel],
                     favorites: set[str],
                     epg_lookup=None) -> None:
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
            card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self._grid.addWidget(card, i // self._columns, i % self._columns)
            self._cards.append(card)
        # keep the last row left-aligned
        self._grid.setColumnStretch(self._columns, 1)

    def update_favorite(self, channel_url: str, fav: bool) -> None:
        for card in self._cards:
            if card.channel.url == channel_url:
                card.set_favorite(fav)

    def mark_selected(self, channel_url: str | None) -> None:
        for card in self._cards:
            card.set_selected(card.channel.url == channel_url)


# -- poster card (continue watching) --------------------------------------------

class PosterCard(QFrame):
    clicked = Signal(object)  # Channel

    def __init__(self, channel: Channel, progress: float = 0.0,
                 subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.channel = channel
        self.setObjectName("posterCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(200)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.art = QLabel()
        self.art.setPixmap(poster_pixmap(200, 190, channel.name, channel.url))
        self.art.setFixedHeight(190)
        lay.addWidget(self.art)

        body = QVBoxLayout()
        body.setContentsMargins(12, 10, 12, 12)
        body.setSpacing(4)
        title = QLabel(channel.name)
        title.setObjectName("cardName")
        title.setWordWrap(True)
        body.addWidget(title)
        self.sub = QLabel(subtitle or channel.display_group)
        self.sub.setObjectName("cardMeta")
        body.addWidget(self.sub)
        self.bar = QProgressBar()
        self.bar.setObjectName("miniProgress")
        self.bar.setRange(0, 100)
        self.bar.setValue(int(progress * 100))
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        body.addWidget(self.bar)
        lay.addLayout(body)

    def set_progress(self, progress: float, subtitle: str = "") -> None:
        self.bar.setValue(int(max(0.0, min(1.0, progress)) * 100))
        if subtitle:
            self.sub.setText(subtitle)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.channel)
        super().mousePressEvent(event)


# -- hero card -------------------------------------------------------------------

class HeroCard(QFrame):
    watch_clicked = Signal(object)
    details_clicked = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("heroCard")
        self.setMinimumHeight(230)
        self._channel: Channel | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        self.live_badge = QLabel('<span style="font-size:9px;">●</span> LIVE')
        self.live_badge.setObjectName("liveBadge")
        top_row.addWidget(self.live_badge)
        self.kicker = QLabel("FEATURED")
        self.kicker.setObjectName("heroKicker")
        top_row.addWidget(self.kicker)
        top_row.addStretch(1)
        left.addLayout(top_row)

        self.title = QLabel("Load a playlist to get started")
        self.title.setObjectName("heroTitle")
        self.title.setWordWrap(True)
        left.addWidget(self.title)
        self.subtitle = QLabel("Add an M3U playlist to browse live TV, movies and series.")
        self.subtitle.setObjectName("cardMeta")
        self.subtitle.setWordWrap(True)
        left.addWidget(self.subtitle)
        left.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        self.watch_btn = QPushButton("  Watch Live")
        self.watch_btn.setObjectName("primaryBtn")
        self.watch_btn.setIcon(make_icon("play", 16, "white"))
        self.watch_btn.setCursor(Qt.PointingHandCursor)
        self.watch_btn.clicked.connect(
            lambda: self._channel and self.watch_clicked.emit(self._channel))
        btn_row.addWidget(self.watch_btn)
        self.details_btn = QPushButton("View Details")
        self.details_btn.setObjectName("outlineBtn")
        self.details_btn.setCursor(Qt.PointingHandCursor)
        self.details_btn.clicked.connect(
            lambda: self._channel and self.details_clicked.emit(self._channel))
        btn_row.addWidget(self.details_btn)
        btn_row.addStretch(1)
        left.addLayout(btn_row)
        lay.addLayout(left, 1)

        self.art = QLabel()
        self.art.setFixedSize(320, 190)
        self.art.setPixmap(poster_pixmap(320, 190, "", "hero-empty"))
        lay.addWidget(self.art)

    def set_feature(self, channel: Channel | None,
                    now: EPGProgram | None = None) -> None:
        self._channel = channel
        has = channel is not None
        self.watch_btn.setEnabled(has)
        self.details_btn.setEnabled(has)
        self.live_badge.setVisible(has and channel.kind == "live")
        if not has:
            self.title.setText("Load a playlist to get started")
            self.subtitle.setText(
                "Add an M3U playlist to browse live TV, movies and series.")
            self.kicker.setText("FEATURED")
            self.art.setPixmap(poster_pixmap(320, 190, "", "hero-empty"))
            return
        self.kicker.setText(channel.display_group.upper())
        self.title.setText(channel.name)
        sub = "Live coverage"
        if now:
            sub = f"{now.title}  •  {now.start.strftime('%H:%M')}–{now.stop.strftime('%H:%M')}"
        elif channel.kind != "live":
            sub = channel.display_group
        self.subtitle.setText(sub)
        self.art.setPixmap(poster_pixmap(320, 190, channel.name, channel.url))
