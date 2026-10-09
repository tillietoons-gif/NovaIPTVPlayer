"""Reusable widgets for the Nova IPTV dashboard.

All icons are drawn with QPainter (no image files, no emojis).
"""

from __future__ import annotations

import hashlib
import math

import requests
from PySide6.QtCore import (
    Qt, Signal, Slot, QRunnable, QThreadPool, QObject,
    QPoint, QPointF, QRect, QRectF, QSize, QTimer, QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QIcon, QPen, QLinearGradient,
    QFont, QFontMetrics, QPainterPath,
)
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QWidget, QLineEdit, QSizePolicy,
    QProgressBar,
)

from app.models import Channel, EPGProgram
from ui.theme import COLORS, animations_enabled


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
    elif name in ("back", "arrow_left"):
        line(0.72, 0.50, 0.28, 0.50)
        p.drawPolyline([
            QPointF(s * 0.48, s * 0.30),
            QPointF(s * 0.28, s * 0.50),
            QPointF(s * 0.48, s * 0.70),
        ])
    elif name == "compress":
        line(0.24, 0.46, 0.46, 0.46)
        line(0.46, 0.24, 0.46, 0.46)
        line(0.24, 0.24, 0.46, 0.46)
        line(0.76, 0.54, 0.54, 0.54)
        line(0.54, 0.76, 0.54, 0.54)
        line(0.76, 0.76, 0.54, 0.54)
    elif name == "volume":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon([
            QPointF(s * 0.18, s * 0.38),
            QPointF(s * 0.34, s * 0.38),
            QPointF(s * 0.50, s * 0.22),
            QPointF(s * 0.50, s * 0.78),
            QPointF(s * 0.34, s * 0.62),
            QPointF(s * 0.18, s * 0.62),
        ])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(s * 0.44, s * 0.32, s * 0.26, s * 0.36), -50 * 16, 100 * 16)
        p.drawArc(QRectF(s * 0.44, s * 0.20, s * 0.40, s * 0.60), -50 * 16, 100 * 16)
    elif name == "mute":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon([
            QPointF(s * 0.18, s * 0.38),
            QPointF(s * 0.34, s * 0.38),
            QPointF(s * 0.50, s * 0.22),
            QPointF(s * 0.50, s * 0.78),
            QPointF(s * 0.34, s * 0.62),
            QPointF(s * 0.18, s * 0.62),
        ])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        line(0.64, 0.36, 0.82, 0.64)
        line(0.82, 0.36, 0.64, 0.64)
    elif name == "trash":
        line(0.38, 0.24, 0.62, 0.24)                      # lid
        line(0.32, 0.24, 0.68, 0.24)
        line(0.46, 0.24, 0.46, 0.18)
        line(0.46, 0.18, 0.54, 0.18)                      # handle
        p.drawRoundedRect(QRectF(s * 0.30, s * 0.30, s * 0.40, s * 0.50),
                          3, 3)                           # bin
        line(0.42, 0.40, 0.42, 0.68)
        line(0.50, 0.40, 0.50, 0.68)
        line(0.58, 0.40, 0.58, 0.68)
    elif name == "lock":
        p.drawPolyline([QPointF(s * 0.36, s * 0.50),     # shackle
                        QPointF(s * 0.36, s * 0.34),
                        QPointF(s * 0.64, s * 0.34),
                        QPointF(s * 0.64, s * 0.50)])
        p.drawRoundedRect(QRectF(s * 0.28, s * 0.46, s * 0.44, s * 0.36),
                          4, 4)                           # body
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(s * 0.50, s * 0.62),
                      s * 0.04, s * 0.04)                 # keyhole
    elif name == "rec":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(s * 0.50, s * 0.50),
                      s * 0.30, s * 0.30)                 # record dot
    elif name in ("help", "question"):
        p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        p.drawArc(QRectF(s * 0.38, s * 0.30, s * 0.24, s * 0.20), 0, 180 * 16)
        line(0.62, 0.40, 0.50, 0.52)
        line(0.50, 0.52, 0.50, 0.60)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QRectF(s * 0.46, s * 0.68, s * 0.08, s * 0.08))
    elif name == "aspect":
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.26, s * 0.68, s * 0.48), 3, 3)
        line(0.32, 0.44, 0.44, 0.56)
        line(0.44, 0.44, 0.32, 0.56)
        line(0.56, 0.44, 0.68, 0.56)
    elif name == "pip":
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.22, s * 0.68, s * 0.56), 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(s * 0.48, s * 0.46, s * 0.30, s * 0.26), 2, 2)
    elif name in ("subtitle", "cc"):
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.26, s * 0.68, s * 0.48), 4, 4)
        line(0.32, 0.42, 0.46, 0.42)
        line(0.32, 0.50, 0.46, 0.50)
        line(0.32, 0.58, 0.46, 0.58)
        line(0.54, 0.42, 0.68, 0.42)
        line(0.54, 0.50, 0.68, 0.50)
        line(0.54, 0.58, 0.68, 0.58)
    elif name in ("calendar", "epg"):
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.56), 4, 4)
        line(0.20, 0.40, 0.80, 0.40)
        line(0.35, 0.18, 0.35, 0.28)
        line(0.65, 0.18, 0.65, 0.28)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRect(QRectF(s * 0.32, s * 0.48, s * 0.10, s * 0.08))
        p.drawRect(QRectF(s * 0.48, s * 0.48, s * 0.10, s * 0.08))
        p.drawRect(QRectF(s * 0.32, s * 0.62, s * 0.10, s * 0.08))
        p.drawRect(QRectF(s * 0.48, s * 0.62, s * 0.10, s * 0.08))
    elif name in ("external", "launch"):
        line(0.28, 0.42, 0.28, 0.74)
        line(0.28, 0.74, 0.72, 0.74)
        line(0.72, 0.74, 0.72, 0.48)
        line(0.46, 0.54, 0.72, 0.28)
        line(0.54, 0.28, 0.72, 0.28)
        line(0.72, 0.28, 0.72, 0.46)
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

_IMAGE_CACHE: dict[str, QImage] = {}
_MAX_IMAGE_CACHE = 600


class _ImageSignals(QObject):
    done = Signal(str, QImage)


class _ImageLoader(QRunnable):
    """Fetch a logo off-thread so scrolling never blocks on the network."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.signals = _ImageSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # runs in a worker thread
        if self.url in _IMAGE_CACHE:
            self.signals.done.emit(self.url, _IMAGE_CACHE[self.url])
            return
        try:
            resp = requests.get(self.url, timeout=8,
                                headers={"User-Agent": "NovaIPTV/1.0"})
            resp.raise_for_status()
            img = QImage.fromData(resp.content)
            if not img.isNull():
                self.signals.done.emit(self.url, img)
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
    """QLabel that loads a remote logo asynchronously with in-memory caching and placeholder."""

    _pool = QThreadPool.globalInstance()

    def __init__(self, size: int = 56, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._url = ""
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(_placeholder_pixmap(size))
        self._loader: _ImageLoader | None = None

    def load(self, url: str) -> None:
        self._url = url or ""
        if not url:
            self.setPixmap(_placeholder_pixmap(self._size))
            return
        if url in _IMAGE_CACHE:
            self._apply_image(_IMAGE_CACHE[url])
            return

        self.setPixmap(_placeholder_pixmap(self._size))
        self._loader = _ImageLoader(url)
        self._loader.signals.done.connect(self._on_image)
        self._pool.start(self._loader)

    def _apply_image(self, img: QImage) -> None:
        pix = QPixmap.fromImage(img).scaled(
            self._size, self._size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self.setPixmap(pix)

    def _on_image(self, url: str, img: QImage) -> None:
        if url:
            if len(_IMAGE_CACHE) >= _MAX_IMAGE_CACHE:
                try:
                    _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
                except (StopIteration, KeyError):
                    pass
            _IMAGE_CACHE[url] = img
        if self._url == url:
            self._apply_image(img)


# -- small building blocks ----------------------------------------------------

class NavButton(QPushButton):
    def __init__(self, icon_name: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("navBtn")
        self.setCheckable(True)
        self._icon_name = icon_name
        self._label = text
        self._compact = False
        self.setIcon(make_icon(icon_name, 20))
        self.setIconSize(QSize(20, 20))
        self.setText(f"  {text}")
        self.setCursor(Qt.PointingHandCursor)

    def set_compact(self, compact: bool) -> None:
        """Icon-rail mode: hide the text label, keep icon + tooltip."""
        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            self.setText("")
            self.setToolTip(self._label)
            self.setFixedWidth(46)
        else:
            self.setText(f"  {self._label}")
            self.setToolTip("")
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)


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
        self.setPlaceholderText("Search channels, movies, series... (/ to focus)")
        self.setClearButtonEnabled(True)


class ElidedLabel(QLabel):
    """QLabel that truncates long text with an ellipsis on resize."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text or ""
        super().setText(self._elided())

    def fullText(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        super().setText(self._elided())

    def _elided(self) -> str:
        fm = QFontMetrics(self.font())
        return fm.elidedText(self._full, Qt.ElideRight, max(20, self.width() - 6))


class SkeletonCard(QFrame):
    """Shimmer-style loading placeholder.

    Cheap opacity pulse driven by a QTimer (no heavy graphics effects);
    static when animations are reduced.
    """

    def __init__(self, width: int = 172, height: int = 200,
                 parent=None, animate: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("skeletonCard")
        self.setFixedSize(width, height)
        self._phase = 0
        self._timer = None
        if animate:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._pulse)
            self._timer.start(650)

    def _pulse(self) -> None:
        self._phase ^= 1
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        base = QColor(COLORS["card"])
        lite = QColor("#2b3242")
        c = lite if self._phase else base
        p.setBrush(c)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        inner = QColor("#313847") if self._phase else QColor("#262c3b")
        p.setBrush(inner)
        w = self.width()
        p.drawRoundedRect(14, 14, w - 28, 84, 8, 8)
        p.drawRoundedRect(14, 110, w - 28, 13, 6, 6)
        p.drawRoundedRect(14, 131, (w - 28) * 2 // 3, 11, 5, 5)


class EmptyState(QWidget):
    """Friendly empty state: drawn icon, title, subtitle, optional CTA."""

    def __init__(self, icon_name: str = "tv", title: str = "",
                 subtitle: str = "", cta_text: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setContentsMargins(24, 32, 24, 32)

        wrap = QFrame()
        wrap.setObjectName("emptyWrap")
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignCenter)
        wl.setSpacing(8)
        wl.setContentsMargins(36, 36, 36, 36)

        ic = QLabel()
        ic.setPixmap(make_icon(icon_name, 46, COLORS["muted"]).pixmap(46, 46))
        ic.setAlignment(Qt.AlignCenter)
        wl.addWidget(ic)

        t = QLabel(title)
        t.setObjectName("emptyTitle")
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        wl.addWidget(t)

        s = QLabel(subtitle)
        s.setObjectName("emptySub")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        wl.addWidget(s)

        self.cta: QPushButton | None = None
        if cta_text:
            self.cta = QPushButton(cta_text)
            self.cta.setObjectName("primaryBtn")
            self.cta.setCursor(Qt.PointingHandCursor)
            wl.addWidget(self.cta, alignment=Qt.AlignCenter)

        lay.addWidget(wrap, alignment=Qt.AlignCenter)


class _Scrim(QWidget):
    """Dimmed backdrop that closes the drawer on click."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class Drawer(QObject):
    """Right-side overlay drawer with dimmed backdrop.

    Content widget is supplied by the caller (reparented in/out).
    Slide animation honors the reduce-animations preference.
    """

    def __init__(self, host: QWidget, width: int = 320) -> None:
        super().__init__(host)
        self._animations_enabled = animations_enabled
        self._host = host
        self._width = width
        self._open = False

        self._scrim = _Scrim(host)
        self._scrim.setObjectName("scrim")
        self._scrim.hide()
        self._scrim.clicked.connect(self.hide)

        self.panel = QWidget(host)
        self.panel.setObjectName("drawerPanel")
        self.panel.hide()
        self._lay = QVBoxLayout(self.panel)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        self._anim = QPropertyAnimation(self.panel, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # -- content ------------------------------------------------------------
    def set_content(self, widget: QWidget) -> None:
        while self._lay.count():
            self._lay.takeAt(0)
        self._lay.addWidget(widget)
        widget.show()

    def take_content(self) -> QWidget | None:
        item = self._lay.takeAt(0)
        w = item.widget() if item else None
        return w

    # -- geometry -----------------------------------------------------------
    def layout_host(self) -> None:
        r = self._host.rect()
        self._scrim.setGeometry(r)
        x = r.width() - self._width if self._open else r.width() + 1
        self.panel.setGeometry(x, 0, self._width, r.height())

    # -- show / hide --------------------------------------------------------
    def is_open(self) -> bool:
        return self._open

    def show(self) -> None:
        r = self._host.rect()
        self._scrim.setGeometry(r)
        self._scrim.show()
        self._scrim.raise_()
        # start just off-screen right, then slide in
        self.panel.setGeometry(r.width() + 1, 0, self._width, r.height())
        self.panel.show()
        self.panel.raise_()
        self._open = True
        if not self._animations_enabled():
            self.panel.move(r.width() - self._width, 0)
            return
        self._anim.stop()
        self._anim.setStartValue(self.panel.pos())
        self._anim.setEndValue(QPoint(
            r.width() - self._width, 0))
        self._anim.start()

    def hide(self) -> None:
        if not self._open and not self.panel.isVisible():
            return
        self._open = False
        if not self._animations_enabled():
            self.panel.hide()
            self._scrim.hide()
            return
        self._anim.stop()
        try:
            self._anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._anim.finished.connect(self._on_hide_finished)
        self._anim.setStartValue(self.panel.pos())
        self._anim.setEndValue(QPoint(self._host.width() + 1, 0))
        self._anim.start()

    def hide_now(self) -> None:
        """Instantly close without animation (mode switches)."""
        self._open = False
        try:
            self._anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._anim.stop()
        self.panel.hide()
        self._scrim.hide()

    def _on_hide_finished(self) -> None:
        try:
            self._anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.panel.hide()
        self._scrim.hide()


# -- video display ---------------------------------------------------------------

class VideoWidget(QWidget):
    """Displays decoded video frames from the player engine with aspect ratio and subtitle overlay."""

    def __init__(self, parent=None, placeholder: str = "No signal") -> None:
        super().__init__(parent)
        self.setObjectName("videoFrame")
        self._pixmap: QPixmap | None = None
        self._placeholder = placeholder
        self._aspect_ratio: str = "auto"  # auto | 16:9 | 4:3 | fill
        self._subtitle_text: str = ""

    @Slot(QImage)
    def set_frame(self, img: QImage) -> None:
        if img.isNull():
            return
        self._pixmap = QPixmap.fromImage(img)
        self.update()  # schedule a repaint in the GUI thread

    def set_aspect_ratio(self, ratio: str) -> None:
        self._aspect_ratio = (ratio or "auto").lower()
        self.update()

    def aspect_ratio(self) -> str:
        return self._aspect_ratio

    def set_subtitle(self, text: str) -> None:
        self._subtitle_text = text or ""
        self.update()

    def clear(self) -> None:
        """Forget the last frame and show the placeholder again."""
        self._pixmap = None
        self._subtitle_text = ""
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._pixmap is not None and not self._pixmap.isNull():
            w, h = self.width(), self.height()
            mode = self._aspect_ratio
            if mode == "fill":
                painter.drawPixmap(self.rect(), self._pixmap)
            elif mode == "16:9":
                target_ratio = 16.0 / 9.0
                if w / max(1, h) > target_ratio:
                    target_w = int(h * target_ratio)
                    target_h = h
                else:
                    target_w = w
                    target_h = int(w / target_ratio)
                x = (w - target_w) // 2
                y = (h - target_h) // 2
                painter.drawPixmap(QRect(x, y, target_w, target_h), self._pixmap)
            elif mode == "4:3":
                target_ratio = 4.0 / 3.0
                if w / max(1, h) > target_ratio:
                    target_w = int(h * target_ratio)
                    target_h = h
                else:
                    target_w = w
                    target_h = int(w / target_ratio)
                x = (w - target_w) // 2
                y = (h - target_h) // 2
                painter.drawPixmap(QRect(x, y, target_w, target_h), self._pixmap)
            else:  # auto
                scaled = self._pixmap.scaled(
                    self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (w - scaled.width()) // 2
                y = (h - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)

            # Draw subtitle overlay
            if self._subtitle_text:
                painter.setRenderHint(QPainter.Antialiasing)
                f = QFont("Segoe UI", 12)
                f.setBold(True)
                painter.setFont(f)
                fm = QFontMetrics(f)
                text_rect = fm.boundingRect(
                    QRect(20, h - 85, w - 40, 65),
                    Qt.AlignCenter | Qt.TextWordWrap,
                    self._subtitle_text,
                )
                bg_rect = text_rect.adjusted(-10, -4, 10, 4)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 190))
                painter.drawRoundedRect(bg_rect, 6, 6)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(
                    text_rect,
                    Qt.AlignCenter | Qt.TextWordWrap,
                    self._subtitle_text,
                )
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

        self.lock_badge = QLabel(self)
        self.lock_badge.setObjectName("lockBadge")
        self.lock_badge.setPixmap(
            make_icon("lock", 14, COLORS["text"]).pixmap(14, 14))
        self.lock_badge.setAlignment(Qt.AlignCenter)
        self.lock_badge.setFixedSize(24, 24)
        self.lock_badge.setVisible(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.live_badge.adjustSize()
        self.live_badge.move(6, 6)
        self.quality_badge.adjustSize()
        self.quality_badge.move(
            self.width() - self.quality_badge.width() - 6, 6)
        # lock badge sits bottom-right, clear of the quality badge
        self.lock_badge.move(self.width() - 30, self.height() - 30)

    def set_locked(self, locked: bool) -> None:
        self.lock_badge.setVisible(locked)


class ChannelCard(QFrame):
    clicked = Signal(object)            # Channel
    fav_toggled = Signal(object, bool)  # Channel, new_state
    context_menu_requested = Signal(object, object)  # Channel, global_pos

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

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.context_menu_requested.emit(self.channel, event.globalPos())
        event.accept()

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

    def set_locked(self, locked: bool) -> None:
        """Show/hide the parental-lock badge on the channel's logo."""
        self.area.set_locked(locked)


class ChannelGrid(QWidget):
    """Scrollable grid of ChannelCards with responsive column count.

    Columns are recomputed from the available viewport width
    (target card min-width ~170px, clamped to 2..6) on resize.
    Re-layout preserves scroll position and card selection.
    """

    channel_chosen = Signal(object)
    fav_toggled = Signal(object, bool)
    channel_context_menu = Signal(object, object)  # Channel, global_pos

    CARD_MIN_WIDTH = 170
    CARD_SPACING = 12
    MIN_COLUMNS = 2
    MAX_COLUMNS = 6
    PAGE_SIZE = 60

    def __init__(self, parent=None, columns: int = 4) -> None:
        super().__init__(parent)
        self._columns = columns
        self._max_columns = self.MAX_COLUMNS
        self._cards: list[ChannelCard] = []
        self._selected_url: str | None = None
        self._locked_groups: set[str] = set()
        self._skeletons: list[SkeletonCard] = []
        self._empty_state: EmptyState | None = None
        self._load_more_button: QPushButton | None = None
        self._channels: list[Channel] = []
        self._favorites: set[str] = set()
        self._epg_lookup = None
        self._rl_timer: QTimer | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setSpacing(self.CARD_SPACING)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self._inner)

    # -- responsive columns -------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._rl_timer is None:
            self._rl_timer = QTimer(self)
            self._rl_timer.setSingleShot(True)
            self._rl_timer.setInterval(90)
            self._rl_timer.timeout.connect(self._relayout)
        self._rl_timer.start()

    def _columns_for_width(self, width: int) -> int:
        if width <= 0:
            return self._columns
        cols = width // (self.CARD_MIN_WIDTH + self.CARD_SPACING)
        cols = max(self.MIN_COLUMNS, min(self.MAX_COLUMNS, cols))
        return min(cols, self._max_columns)

    def set_max_columns(self, n: int) -> None:
        """Cap the column count (used by the <900px breakpoint)."""
        n = max(self.MIN_COLUMNS, min(self.MAX_COLUMNS, n))
        if n != self._max_columns:
            self._max_columns = n
            self._relayout()

    def _relayout(self) -> None:
        cols = self._columns_for_width(self.scroll.viewport().width())
        if cols == self._columns:
            return
        bar = self.scroll.verticalScrollBar()
        pos = bar.value()
        old = self._columns
        self._grid.setColumnStretch(old, 0)
        for card in self._cards:
            self._grid.removeWidget(card)
        self._columns = cols
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // cols, i % cols)
        if self._load_more_button is not None:
            self._grid.removeWidget(self._load_more_button)
            row = (len(self._cards) + cols - 1) // cols
            self._grid.addWidget(self._load_more_button, row, 0, 1, cols)
        self._grid.setColumnStretch(cols, 1)
        # restore scroll once the layout settles, keep selection
        QTimer.singleShot(0, lambda: bar.setValue(min(pos, bar.maximum())))
        self.mark_selected(self._selected_url)

    # -- content ------------------------------------------------------------
    def _take_all(self) -> None:
        for card in self._cards:
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        for sk in self._skeletons:
            self._grid.removeWidget(sk)
            sk.deleteLater()
        self._skeletons.clear()
        if self._load_more_button is not None:
            self._grid.removeWidget(self._load_more_button)
            self._load_more_button.deleteLater()
            self._load_more_button = None
        if self._empty_state is not None:
            self._grid.removeWidget(self._empty_state)
            self._empty_state.deleteLater()
            self._empty_state = None
        self._channels = []
        self._favorites.clear()
        self._epg_lookup = None

    def show_skeletons(self, count: int = 8) -> None:
        """Show shimmer placeholders while content loads."""
        self._take_all()
        cols = self._columns_for_width(self.scroll.viewport().width())
        self._columns = cols
        for i in range(count):
            sk = SkeletonCard(animate=animations_enabled())
            self._grid.addWidget(sk, i // cols, i % cols)
            self._skeletons.append(sk)
        self._grid.setColumnStretch(cols, 1)

    def set_channels(self, channels: list[Channel],
                     favorites: set[str],
                     epg_lookup=None, *,
                     empty_title: str = "No channels",
                     empty_sub: str = "Load a playlist to get started.",
                     cta_text: str = "",
                     cta_slot=None) -> None:
        self._take_all()
        self._channels = list(channels)
        self._favorites = set(favorites)
        self._epg_lookup = epg_lookup

        if not channels:
            self._empty_state = EmptyState(
                "tv", empty_title, empty_sub, cta_text)
            if cta_text and cta_slot and self._empty_state.cta:
                self._empty_state.cta.clicked.connect(cta_slot)
            self._grid.addWidget(self._empty_state, 0, 0, 1, self._columns)
            return

        cols = self._columns_for_width(self.scroll.viewport().width())
        self._columns = cols
        self._append_channels()

    def _append_channels(self) -> None:
        start = len(self._cards)
        end = min(start + self.PAGE_SIZE, len(self._channels))
        cols = self._columns
        for i in range(start, end):
            ch = self._channels[i]
            epg_text = ""
            if self._epg_lookup is not None:
                try:
                    epg_text = self._epg_lookup(ch) or ""
                except Exception:
                    epg_text = ""
            card = ChannelCard(ch, ch.url in self._favorites, epg_text)
            card.clicked.connect(self.channel_chosen.emit)
            card.fav_toggled.connect(self.fav_toggled.emit)
            card.context_menu_requested.connect(self.channel_context_menu.emit)
            card.set_locked(ch.display_group in self._locked_groups)
            card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self._grid.addWidget(card, i // cols, i % cols)
            self._cards.append(card)

        if end < len(self._channels):
            remaining = len(self._channels) - end
            button = QPushButton(
                f"Load {min(self.PAGE_SIZE, remaining)} more "
                f"({remaining} remaining)")
            button.setObjectName("outlineBtn")
            button.clicked.connect(self._append_more)
            row = (end + cols - 1) // cols
            self._grid.addWidget(button, row, 0, 1, cols)
            self._load_more_button = button

        self._grid.setColumnStretch(cols, 1)
        self.mark_selected(self._selected_url)

    def _append_more(self) -> None:
        if self._load_more_button is not None:
            self._grid.removeWidget(self._load_more_button)
            self._load_more_button.deleteLater()
            self._load_more_button = None
        self._append_channels()

    def update_favorite(self, channel_url: str, fav: bool) -> None:
        if fav:
            self._favorites.add(channel_url)
        else:
            self._favorites.discard(channel_url)
        for card in self._cards:
            if card.channel.url == channel_url:
                card.set_favorite(fav)

    def mark_selected(self, channel_url: str | None) -> None:
        self._selected_url = channel_url
        for card in self._cards:
            card.set_selected(card.channel.url == channel_url)

    def set_locked_groups(self, groups: set[str]) -> None:
        """Remember which categories are locked and refresh all badges."""
        self._locked_groups = set(groups)
        self.refresh_locks()

    def refresh_locks(self) -> None:
        for card in self._cards:
            card.set_locked(card.channel.display_group in self._locked_groups)


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
        self._stacked = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._body = QWidget()
        outer.addWidget(self._body)

        lay = QHBoxLayout(self._body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(24)
        self._left = QWidget()
        left = QVBoxLayout(self._left)
        left.setContentsMargins(0, 0, 0, 0)
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
        lay.addWidget(self._left, 1)

        self.art = QLabel()
        self.art.setFixedSize(320, 190)
        self.art.setPixmap(poster_pixmap(320, 190, "", "hero-empty"))
        self._body_layout = lay
        lay.addWidget(self.art)

    def set_stacked(self, stacked: bool) -> None:
        """Stack text above art on narrow content (<1100px)."""
        if stacked == self._stacked:
            return
        self._stacked = stacked
        lay = self._body_layout
        # detach children
        lay.removeWidget(self._left)
        lay.removeWidget(self.art)
        # swap orientation by rebuilding the body layout
        old = self._body.layout()
        QWidget().setLayout(old)  # orphan old layout
        if stacked:
            new_lay = QVBoxLayout(self._body)
        else:
            new_lay = QHBoxLayout(self._body)
        new_lay.setContentsMargins(28, 24, 28, 24)
        new_lay.setSpacing(16 if stacked else 24)
        new_lay.addWidget(self._left, 1 if not stacked else 0)
        if stacked:
            new_lay.addWidget(self.art, 0, Qt.AlignHCenter)
        else:
            new_lay.addWidget(self.art)
        self._body_layout = new_lay

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
