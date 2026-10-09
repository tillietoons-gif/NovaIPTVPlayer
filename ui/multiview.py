"""Multi-View (Quad-Screen / Split-Screen) grid player for sports and live news."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QMenu
)

from app.models import Channel
from app.player import Player
from ui.theme import COLORS
from ui.widgets import VideoWidget, make_icon

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class MultiViewTile(QFrame):
    """A single interactive live stream tile within the Multi-View grid."""

    tile_clicked = Signal(object)      # self (for audio focus)
    tile_maximized = Signal(object)    # self
    channel_change_requested = Signal(object) # self

    def __init__(self, tile_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tile_id = tile_id
        self.channel: Channel | None = None
        self.player = Player(self)
        self.is_audio_active = False
        self.is_maximized = False

        self.setObjectName("multiViewTile")
        self.setStyleSheet(f"""
            QFrame#multiViewTile {{
                background-color: {COLORS['surface']};
                border: 2px solid {COLORS['border']};
                border-radius: 12px;
            }}
            QFrame#multiViewTile[audioActive="true"] {{
                border: 2px solid {COLORS['accent']};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # Header bar
        self.header = QWidget()
        self.header.setFixedHeight(34)
        h_lay = QHBoxLayout(self.header)
        h_lay.setContentsMargins(6, 2, 6, 2)
        h_lay.setSpacing(6)

        self.title_lbl = QLabel(f"Stream #{tile_id + 1} — Empty")
        self.title_lbl.setStyleSheet("color: white; font-weight: 700; font-size: 9.5pt;")
        h_lay.addWidget(self.title_lbl, 1)

        self.audio_badge = QLabel("🔇")
        self.audio_badge.setToolTip("Click tile to switch audio focus")
        self.audio_badge.setStyleSheet(f"color: {COLORS['muted']}; font-size: 11pt;")
        h_lay.addWidget(self.audio_badge)

        self.change_btn = QPushButton()
        self.change_btn.setIcon(make_icon("zap", 14, COLORS["accent"]))
        self.change_btn.setFixedSize(26, 26)
        self.change_btn.setToolTip("Change Channel")
        self.change_btn.setCursor(Qt.PointingHandCursor)
        self.change_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface2']};
                border: 1px solid {COLORS['border']};
                border-radius: 13px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
            }}
        """)
        self.change_btn.clicked.connect(lambda: self.channel_change_requested.emit(self))
        h_lay.addWidget(self.change_btn)

        self.max_btn = QPushButton()
        self.max_btn.setIcon(make_icon("maximize", 12, COLORS["muted"]))
        self.max_btn.setFixedSize(26, 26)
        self.max_btn.setToolTip("Maximize / Restore tile")
        self.max_btn.setCursor(Qt.PointingHandCursor)
        self.max_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface2']};
                border: 1px solid {COLORS['border']};
                border-radius: 13px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
            }}
        """)
        self.max_btn.clicked.connect(lambda: self.tile_maximized.emit(self))
        h_lay.addWidget(self.max_btn)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(make_icon("close", 12, COLORS["muted"]))
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("Close / Clear stream")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['surface2']};
                border: 1px solid {COLORS['border']};
                border-radius: 13px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['red']};
            }}
        """)
        self.close_btn.clicked.connect(self.clear_stream)
        h_lay.addWidget(self.close_btn)

        lay.addWidget(self.header)

        # Video canvas & empty placeholder
        self.video = VideoWidget(self, placeholder="")
        self.video.setCursor(Qt.PointingHandCursor)
        self.player.attach(self.video)
        self.player.frame_ready.connect(self.video.set_frame)
        lay.addWidget(self.video, 1)

        # Empty state button overlaid inside video
        self.empty_btn = QPushButton("  + Select Channel to Watch", self.video)
        self.empty_btn.setIcon(make_icon("play", 16, COLORS["accent"]))
        self.empty_btn.setCursor(Qt.PointingHandCursor)
        self.empty_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(22, 27, 34, 0.85);
                color: white;
                font-weight: 700;
                font-size: 10.5pt;
                border: 1px solid {COLORS['accent']};
                border-radius: 20px;
                padding: 10px 22px;
            }}
            QPushButton:hover {{
                background: {COLORS['accent']};
                color: white;
            }}
        """)
        self.empty_btn.clicked.connect(lambda: self.channel_change_requested.emit(self))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.empty_btn.adjustSize()
        vx = (self.video.width() - self.empty_btn.width()) // 2
        vy = (self.video.height() - self.empty_btn.height()) // 2
        self.empty_btn.move(max(10, vx), max(10, vy))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self.tile_clicked.emit(self)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        super().mouseDoubleClickEvent(event)
        self.tile_maximized.emit(self)

    def load_channel(self, channel: Channel) -> None:
        """Begin playback of channel on this tile."""
        self.channel = channel
        self.title_lbl.setText(f"#{self.tile_id + 1} • {channel.name}")
        self.empty_btn.hide()
        self.player.play(channel.url, channel.stream_headers)
        if not self.is_audio_active:
            self.player.set_mute(True)

    def clear_stream(self) -> None:
        """Stop playback and reset to empty tile."""
        self.player.stop()
        self.channel = None
        self.title_lbl.setText(f"Stream #{self.tile_id + 1} — Empty")
        self.set_audio_active(False)
        self.video.update()
        self.empty_btn.show()

    def set_audio_active(self, active: bool) -> None:
        """Switch audio unmute focus for this tile."""
        self.is_audio_active = active
        self.player.set_mute(not active)
        self.audio_badge.setText("🔊" if active else "🔇")
        self.audio_badge.setStyleSheet(
            f"color: {COLORS['accent'] if active else COLORS['muted']}; font-size: 11pt;"
        )
        self.setProperty("audioActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    @property
    def _audio_active(self) -> bool:
        return self.is_audio_active


class MultiViewGrid(QWidget):
    """Grid container managing dual, triple, or quad live stream views."""

    channel_selected = Signal(object)
    status_message = Signal(str)

    def __init__(self, main_window: MainWindow | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.main = main_window
        self.current_layout = "quad"  # "dual", "triple", "quad"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(10)

        # Top Control Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        title = QLabel("Multi-View Sports & News")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch(1)

        # Layout selector buttons
        self.dual_btn = QPushButton("Dual (1×2)")
        self.dual_btn.setObjectName("outlineBtn")
        self.dual_btn.setCursor(Qt.PointingHandCursor)
        self.dual_btn.clicked.connect(lambda: self.switch_layout("dual"))
        toolbar.addWidget(self.dual_btn)

        self.triple_btn = QPushButton("Triple (1+2)")
        self.triple_btn.setObjectName("outlineBtn")
        self.triple_btn.setCursor(Qt.PointingHandCursor)
        self.triple_btn.clicked.connect(lambda: self.switch_layout("triple"))
        toolbar.addWidget(self.triple_btn)

        self.quad_btn = QPushButton("Quad (2×2)")
        self.quad_btn.setObjectName("primaryBtn")
        self.quad_btn.setCursor(Qt.PointingHandCursor)
        self.quad_btn.clicked.connect(lambda: self.switch_layout("quad"))
        toolbar.addWidget(self.quad_btn)

        toolbar.addSpacing(12)

        mute_all = QPushButton("Mute All")
        mute_all.setObjectName("outlineBtn")
        mute_all.setCursor(Qt.PointingHandCursor)
        mute_all.clicked.connect(self.mute_all)
        toolbar.addWidget(mute_all)

        stop_all = QPushButton("Stop All")
        stop_all.setObjectName("outlineBtn")
        stop_all.setCursor(Qt.PointingHandCursor)
        stop_all.clicked.connect(self.stop_all)
        toolbar.addWidget(stop_all)

        outer.addLayout(toolbar)

        # Tiles grid layout
        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        outer.addWidget(self.grid_container, 1)

        # Create 4 tiles
        self.tiles: list[MultiViewTile] = []
        for i in range(4):
            tile = MultiViewTile(i, self)
            tile.tile_clicked.connect(self._on_tile_focus)
            tile.tile_maximized.connect(self._on_tile_maximize)
            tile.channel_change_requested.connect(self._on_channel_change)
            self.tiles.append(tile)

        self.switch_layout("quad")

    def switch_layout(self, layout_mode: str) -> None:
        """Switch grid arrangement between dual, triple, and quad."""
        self.current_layout = layout_mode
        self.dual_btn.setObjectName("primaryBtn" if layout_mode == "dual" else "outlineBtn")
        self.triple_btn.setObjectName("primaryBtn" if layout_mode == "triple" else "outlineBtn")
        self.quad_btn.setObjectName("primaryBtn" if layout_mode == "quad" else "outlineBtn")
        for btn in (self.dual_btn, self.triple_btn, self.quad_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Clear existing layout bindings
        for tile in self.tiles:
            self.grid.removeWidget(tile)
            tile.hide()
            tile.is_maximized = False

        if layout_mode == "dual":
            # 2 tiles side-by-side
            self.grid.addWidget(self.tiles[0], 0, 0)
            self.grid.addWidget(self.tiles[1], 0, 1)
            self.tiles[0].show()
            self.tiles[1].show()
        elif layout_mode == "triple":
            # 1 big tile left, 2 stacked right
            self.grid.addWidget(self.tiles[0], 0, 0, 2, 1)
            self.grid.addWidget(self.tiles[1], 0, 1)
            self.grid.addWidget(self.tiles[2], 1, 1)
            self.tiles[0].show()
            self.tiles[1].show()
            self.tiles[2].show()
        else:  # quad
            # 2x2 grid
            self.grid.addWidget(self.tiles[0], 0, 0)
            self.grid.addWidget(self.tiles[1], 0, 1)
            self.grid.addWidget(self.tiles[2], 1, 0)
            self.grid.addWidget(self.tiles[3], 1, 1)
            for t in self.tiles:
                t.show()

    def _on_tile_focus(self, active_tile: MultiViewTile) -> None:
        """Focus audio onto the clicked tile, muting other tiles."""
        for tile in self.tiles:
            tile.set_audio_active(tile is active_tile)

    def _on_tile_maximize(self, target_tile: MultiViewTile) -> None:
        """Toggle maximizing one tile to fill the entire multi-view area."""
        if target_tile.is_maximized:
            # Restore grid
            target_tile.is_maximized = False
            self.switch_layout(self.current_layout)
        else:
            # Maximize this tile
            for tile in self.tiles:
                self.grid.removeWidget(tile)
                tile.hide()
                tile.is_maximized = False
            target_tile.is_maximized = True
            self.grid.addWidget(target_tile, 0, 0)
            target_tile.show()

    def _on_channel_change(self, tile: MultiViewTile) -> None:
        """Prompt user with quick channel picker to assign to this tile."""
        self.channel_selected.emit(tile)
        if hasattr(self.main, "_open_quick_zapper_for_tile"):
            self.main._open_quick_zapper_for_tile(tile)

    def set_layout(self, layout_name: str) -> None:
        """Alias for switch_layout."""
        self.switch_layout(layout_name)

    def set_audio_focus(self, tile_index: int) -> None:
        """Directly focus audio on tile at the given index."""
        if 0 <= tile_index < len(self.tiles):
            self._on_tile_focus(self.tiles[tile_index])

    def mute_all(self) -> None:
        for tile in self.tiles:
            tile.set_audio_active(False)

    def stop_all(self) -> None:
        for tile in self.tiles:
            tile.clear_stream()
