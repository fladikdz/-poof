"""Main window — wires together mode selector, device panel, map, route panel and status bar."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.session import SpoofSession, SpoofState

from .ble_panel import BlePanel
from .device_panel import DevicePanel
from .map_widget import MapWidget
from .mode_selector import ModeSelector
from .route_panel import RoutePanel
from .search_bar import SearchBar
from .status_bar import StatusBar


class AppWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("poof - iOS Location Spoofer")
        self.resize(1200, 760)

        self._session = SpoofSession(self)

        # ---- widgets ---------------------------------------------------
        self._search_bar = SearchBar()
        self._mode_selector = ModeSelector()
        self._device_panel = DevicePanel(self._session)
        self._map = MapWidget()
        self._route_panel = RoutePanel()
        self._ble_panel = BlePanel()
        self._status = StatusBar()

        # ---- left sidebar (search + mode picker + device list + BLE) -----
        sidebar = QWidget()
        sidebar_lyt = QVBoxLayout(sidebar)
        sidebar_lyt.setContentsMargins(8, 8, 8, 8)
        sidebar_lyt.addWidget(self._search_bar)
        sidebar_lyt.addWidget(self._mode_selector)
        sidebar_lyt.addWidget(self._device_panel, 1)
        sidebar_lyt.addWidget(self._ble_panel)

        # ---- right sidebar (mode-dependent: empty for teleport, route panel for route) ----
        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(QWidget())          # index 0: teleport (empty)
        self._right_stack.addWidget(self._route_panel)  # index 1: route
        # Visibility is controlled by splitter sizes only — don't cap maxWidth,
        # otherwise the route panel can't expand when route mode is selected.

        # ---- main layout ----------------------------------------------
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar)
        splitter.addWidget(self._map)
        splitter.addWidget(self._right_stack)
        splitter.setSizes([280, 920, 0])  # right panel collapsed for teleport mode
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setCollapsible(2, True)
        self._splitter = splitter

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(splitter, 1)
        v.addWidget(self._status)
        self.setCentralWidget(container)

        # ---- signal wiring --------------------------------------------
        self._mode_selector.mode_changed.connect(self._on_mode_changed)

        self._map.teleport_requested.connect(self._on_teleport_requested)
        self._map.waypoints_changed.connect(self._route_panel.set_waypoints)
        self._map.route_geometry_changed.connect(self._route_panel.set_route_geometry)

        self._route_panel.start_requested.connect(self._on_route_start_requested)
        self._route_panel.stop_requested.connect(self._on_route_stop_requested)
        self._route_panel.clear_requested.connect(self._on_route_clear_requested)
        self._route_panel.speed_changed.connect(self._session.set_route_speed)

        self._search_bar.search_submitted.connect(self._session.geocode)
        self._search_bar.result_chosen.connect(self._on_search_result_teleport)
        self._search_bar.route_here_chosen.connect(self._on_search_route_here)
        self._session.geocode_results.connect(self._on_geocode_results)

        self._ble_panel.start_requested.connect(self._session.ble_start)
        self._ble_panel.stop_requested.connect(self._session.ble_stop)
        self._ble_panel.generate_test_key_requested.connect(self._session.ble_generate_test_key)
        self._session.ble_state_changed.connect(self._ble_panel.set_state)

        self._status.clear_requested.connect(self._session.clear)

        self._session.spoof_changed.connect(self._on_spoof_changed)
        self._session.error.connect(self._on_error)
        self._session.log_message.connect(self._status.set_log_message)

        self._current_mode = "teleport"

    # ---- handlers ------------------------------------------------------

    def _on_mode_changed(self, mode: str) -> None:
        self._current_mode = mode
        self._map.set_mode(mode)
        w = max(self.width(), 1100)
        if mode == "teleport":
            self._right_stack.setCurrentIndex(0)
            self._splitter.setSizes([280, w - 280, 0])
        else:
            self._right_stack.setCurrentIndex(1)
            self._splitter.setSizes([260, w - 260 - 340, 340])

    def _on_teleport_requested(self, lat: float, lon: float) -> None:
        udid = self._device_panel.selected_udid() or None
        self._session.teleport(lat, lon, udid)

    def _on_route_start_requested(self, waypoints: list, speed_kmh: float) -> None:
        udid = self._device_panel.selected_udid() or None
        self._session.start_route(waypoints, speed_kmh, udid)
        self._route_panel.set_running(True)

    def _on_route_stop_requested(self) -> None:
        self._session.stop_route()
        self._route_panel.set_running(False)

    def _on_route_clear_requested(self) -> None:
        self._session.stop_route()
        self._map.clear_route_waypoints()
        # Don't rely on the JS->Python bridge round-trip to clear the UI list —
        # do it directly so Clear always feels responsive.
        self._route_panel.set_waypoints([])
        self._route_panel.set_running(False)

    def _on_spoof_changed(self, state: Optional[SpoofState]) -> None:
        self._status.set_spoof_state(state)
        if state is None:
            self._map.clear_spoof()
            # Spoof ended — also reset route-running state if route was active.
            self._route_panel.set_running(False)
        else:
            self._map.show_spoof(state.latitude, state.longitude)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "poof - error", message)
        self._status.set_log_message(f"Error: {message.splitlines()[0]}")

    # ---- search-bar handlers -----------------------------------------

    def _on_geocode_results(self, results: list) -> None:
        self._search_bar.set_results(results)
        if results:
            r = results[0]
            self._map.show_search_result(r.latitude, r.longitude, r.name)

    def _on_search_result_teleport(self, lat: float, lon: float, name: str) -> None:
        # 'Teleport here' from a search result — works regardless of current mode.
        self._map.show_search_result(lat, lon, name)
        udid = self._device_panel.selected_udid() or None
        self._session.teleport(lat, lon, udid)

    def _on_search_route_here(self, lat: float, lon: float, name: str) -> None:
        """Build a route from current spoof position to the searched place."""
        start = self._session.current_spoof_position()
        if start is None:
            QMessageBox.information(
                self, "poof",
                "Need a starting position first. Teleport once (or set any spoof) "
                "so we have a 'from' point — then 'Route from here' will route "
                "from that location."
            )
            return

        # Switch into route mode, clear any existing waypoints, then add start+end.
        self._mode_selector.set_mode("route")
        self._on_route_clear_requested()
        self._map.add_waypoint(start[0], start[1])
        self._map.add_waypoint(lat, lon)
        self._map.show_search_result(lat, lon, name)
        self._status.set_log_message(
            f'Building road route from current position to "{name[:60]}"...'
        )

    # ---- shutdown ------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._device_panel.stop_polling()
        self._session.shutdown()
        super().closeEvent(event)
