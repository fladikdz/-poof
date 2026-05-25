"""Right-side route builder — visible when 'Route' mode is selected."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt


class RoutePanel(QWidget):
    """Manages the route plan + speed slider + start/stop buttons."""

    start_requested = Signal(list, float)   # waypoints, speed_kmh
    stop_requested = Signal()
    clear_requested = Signal()
    speed_changed = Signal(float)           # emitted whenever slider moves

    SPEED_MIN_KMH = 1
    SPEED_MAX_KMH = 200
    SPEED_DEFAULT_KMH = 40

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._waypoints: list[tuple[float, float]] = []     # user-clicked pins (1..N)
        self._geometry: list[tuple[float, float]] = []      # road-routed dense path (or fallback)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Route")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("Click on the map to add waypoints in order.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        self._wp_list = QListWidget()
        self._wp_list.setMaximumHeight(180)
        layout.addWidget(self._wp_list, 1)

        # Speed slider
        speed_box = QGroupBox("Speed")
        speed_lyt = QHBoxLayout(speed_box)
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setMinimum(self.SPEED_MIN_KMH)
        self._speed_slider.setMaximum(self.SPEED_MAX_KMH)
        self._speed_slider.setValue(self.SPEED_DEFAULT_KMH)
        self._speed_slider.setTickPosition(QSlider.TicksBelow)
        self._speed_slider.setTickInterval(20)
        self._speed_value = QLabel(f"{self.SPEED_DEFAULT_KMH} km/h")
        self._speed_value.setMinimumWidth(70)

        def _on_speed_value_changed(v: int) -> None:
            self._speed_value.setText(f"{v} km/h")
            self.speed_changed.emit(float(v))

        self._speed_slider.valueChanged.connect(_on_speed_value_changed)
        speed_lyt.addWidget(self._speed_slider, 1)
        speed_lyt.addWidget(self._speed_value)
        layout.addWidget(speed_box)

        # Buttons
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self.clear_requested)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(self._clear_btn)
        layout.addLayout(btn_row)

        layout.addStretch(1)

    # ---- public API ---------------------------------------------------

    def set_waypoints(self, waypoints: list) -> None:
        self._waypoints = [(float(p[0]), float(p[1])) for p in waypoints]
        if len(self._waypoints) < 2:
            # No road geometry without at least 2 points; fall back to the
            # straight line until OSRM (or its fallback) reports something.
            self._geometry = list(self._waypoints)
        self._wp_list.clear()
        for i, (lat, lon) in enumerate(self._waypoints, 1):
            self._wp_list.addItem(QListWidgetItem(f"{i}. {lat:.5f}, {lon:.5f}"))
        ready = len(self._waypoints) >= 2
        self._start_btn.setEnabled(ready)
        self._clear_btn.setEnabled(len(self._waypoints) > 0)

    def set_route_geometry(self, geometry: list) -> None:
        """Dense road-routed points — used as the actual playback path."""
        self._geometry = [(float(p[0]), float(p[1])) for p in geometry]

    def set_running(self, running: bool) -> None:
        """Reflect external playback state: disable Start, enable Stop, etc."""
        self._start_btn.setEnabled(not running and len(self._waypoints) >= 2)
        self._stop_btn.setEnabled(running)

    # ---- handlers -----------------------------------------------------

    def _on_start_clicked(self) -> None:
        if len(self._waypoints) < 2:
            return
        speed = float(self._speed_slider.value())
        # Prefer the road-routed geometry; fall back to user clicks if OSRM
        # never returned (or while it's still in flight).
        path = self._geometry if len(self._geometry) >= 2 else list(self._waypoints)
        self.start_requested.emit(path, speed)
