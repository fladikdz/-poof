"""Leaflet map embedded in a QWebEngineView, with a JS<->Python bridge."""

from __future__ import annotations

from pathlib import Path

import logging

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget, QVBoxLayout

from core.paths import resource_path


logger = logging.getLogger(__name__)


class _LoggingPage(QWebEnginePage):
    """Forwards JS console messages to the Python logger so we can see them."""

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        kind = getattr(level, "name", str(level))
        src = source.rsplit("/", 1)[-1] if isinstance(source, str) else source
        logger.info("JS %s %s:%d  %s", kind, src, line, message)


_MAP_HTML = resource_path("backend", "gui", "assets", "map.html")


class _Bridge(QObject):
    """JS-callable object — Leaflet click + waypoint + route geometry come through here."""

    teleport_requested = Signal(float, float)
    waypoints_changed = Signal(list)        # list[(lat, lon)] — user clicks, for the side list
    route_geometry_changed = Signal(list)   # list[(lat, lon)] — dense road-routed points for playback

    @Slot(float, float)
    def teleport_to(self, lat: float, lon: float) -> None:
        self.teleport_requested.emit(lat, lon)

    @Slot(list)
    def set_waypoints(self, waypoints: list) -> None:
        cleaned = [(float(p[0]), float(p[1])) for p in waypoints if len(p) == 2]
        self.waypoints_changed.emit(cleaned)

    @Slot(list)
    def set_route_geometry(self, geometry: list) -> None:
        cleaned = [(float(p[0]), float(p[1])) for p in geometry if len(p) == 2]
        self.route_geometry_changed.emit(cleaned)


class MapWidget(QWidget):
    """Map panel — emits `teleport_requested(lat, lon)` on user click,
    `waypoints_changed(list)` when the user-clicked plan changes, and
    `route_geometry_changed(list)` when OSRM road-routing produces dense
    playback points (or falls back to the straight-line waypoints)."""

    teleport_requested = Signal(float, float)
    waypoints_changed = Signal(list)
    route_geometry_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = QWebEngineView(self)
        # Use our LoggingPage so JS console messages bubble up to Python logs.
        self._page = _LoggingPage(self._view)
        self._view.setPage(self._page)

        # Loaded via file:// — by default QtWebEngine forbids local pages from
        # loading remote URLs (OSM tiles, etc.). Both flags are needed so map
        # tiles can come through and JS can fetch any external API.
        attrs = QWebEngineSettings.WebAttribute
        s = self._page.settings()
        s.setAttribute(attrs.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(attrs.LocalContentCanAccessFileUrls, True)

        self._bridge = _Bridge(self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._bridge.teleport_requested.connect(self.teleport_requested)
        self._bridge.waypoints_changed.connect(self.waypoints_changed)
        self._bridge.route_geometry_changed.connect(self.route_geometry_changed)

        self._page.loadFinished.connect(
            lambda ok: logger.info("Map page loadFinished: ok=%s", ok)
        )

        self._view.load(QUrl.fromLocalFile(str(_MAP_HTML)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    # ---- methods callable from the main window to drive the JS side ----

    def show_spoof(self, lat: float, lon: float) -> None:
        # JS function defined in map.html
        self._view.page().runJavaScript(f"window.showSpoof({lat}, {lon});")

    def clear_spoof(self) -> None:
        self._view.page().runJavaScript("window.clearSpoof();")

    def set_mode(self, mode: str) -> None:
        """`mode` is 'teleport' or 'route' — controls click behaviour in JS."""
        self._view.page().runJavaScript(f"window.setMode({mode!r});")

    def clear_route_waypoints(self) -> None:
        self._view.page().runJavaScript("window.clearRouteWaypoints();")

    def show_search_result(self, lat: float, lon: float, name: str) -> None:
        # JS-side: drop a distinctive marker and zoom-pan to it.
        # Escape quotes in name for safe embedding.
        safe = name.replace("\\", "\\\\").replace("'", "\\'")
        self._view.page().runJavaScript(
            f"window.showSearchResult({lat}, {lon}, '{safe}');"
        )

    def add_waypoint(self, lat: float, lon: float) -> None:
        """Programmatically add a waypoint (used by 'Route from here')."""
        self._view.page().runJavaScript(f"window.addWaypoint({lat}, {lon});")
