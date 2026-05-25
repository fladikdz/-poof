"""Qt-friendly facade over the existing DVT/tunneld code.

GUI runs in the Qt main thread (sync). `pymobiledevice3` is async-only. We bridge
the two with a worker QThread that owns its own asyncio loop:

  - Main thread posts coroutines via `asyncio.run_coroutine_threadsafe()`.
  - Worker emits Qt signals back when state changes (devices_changed, etc.).
  - The DVT/LocationSimulation session is held inside the worker as a long-lived
    task — opening it is expensive (sets up the tunnel + DVT handshake), so we
    keep it alive across teleport calls and just update the coordinate.

Signals are thread-safe (Qt::QueuedConnection by default for cross-thread signals).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import threading

from PySide6.QtCore import QObject, QThread, Signal

from core.dvt_spoofer import open_location_simulation
from core.ios_manager import (
    UsbmuxUnavailable,
    get_tunneled_rsd,
    list_tunneled_devices,
    list_usb_devices,
)
from core.movement import Waypoint, play_route, total_distance_m

from ble import constants as ble_constants
from ble.transport import PeripheralNotSupported, create_peripheral


logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    udid: str
    label: str            # human-readable: "iPhone15,3 iOS 17.4.1 (Bob's iPhone)"
    connection: str       # "USB" / "Tunneled" / "USB+Tunneled"
    tunneled: bool        # ready for DVT


@dataclass
class SpoofState:
    udid: str
    latitude: float
    longitude: float


@dataclass
class GeocodeResult:
    name: str
    latitude: float
    longitude: float


class _Worker(QObject):
    """Lives in a background QThread, owns the asyncio loop and the DVT session."""

    devices_changed = Signal(list)         # list[DeviceInfo]
    spoof_changed = Signal(object)         # SpoofState | None
    geocode_results = Signal(list)         # list[GeocodeResult]
    ble_state_changed = Signal(str)        # "stopped" | "starting" | "advertising" | "error: ..."
    error = Signal(str)
    log_message = Signal(str)              # human-readable status line for status bar

    def __init__(self) -> None:
        super().__init__()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sim_task: Optional[asyncio.Task] = None
        self._sim_cmd_queue: Optional[asyncio.Queue] = None
        self._current_state: Optional[SpoofState] = None
        self._route_task: Optional[asyncio.Task] = None
        self._route_speed_kmh: float = 40.0  # mutable; UI updates via set_route_speed
        self._ble_peripheral = None         # current BLE peripheral, if running
        self._loop_ready = threading.Event()  # signals once asyncio loop is running

    # ---- thread entry -------------------------------------------------

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()
            self._loop = None

    def wait_for_loop(self, timeout: float = 5.0) -> None:
        if not self._loop_ready.wait(timeout=timeout):
            raise RuntimeError("worker loop did not start within timeout")

    def stop_loop(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ---- public API (call from main thread) --------------------------

    def submit(self, coro):
        loop = self._loop
        if loop is None or not loop.is_running():
            # Loop has been torn down (we're shutting down). Silently swallow
            # the coroutine to avoid log noise and "coroutine was never awaited"
            # warnings.
            coro.close()
            return None
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def refresh_devices(self) -> None:
        self.submit(self._refresh_devices_impl())

    def teleport(self, latitude: float, longitude: float, udid: Optional[str]) -> None:
        self.submit(self._teleport_impl(latitude, longitude, udid))

    def geocode(self, query: str) -> None:
        self.submit(self._geocode_impl(query))

    def ble_start(self) -> None:
        self.submit(self._ble_start_impl())

    def ble_stop(self) -> None:
        self.submit(self._ble_stop_impl())

    def ble_generate_test_key(self) -> None:
        self.submit(self._ble_generate_test_key_impl())

    def start_route(self, waypoints: list, speed_kmh: float, udid: Optional[str]) -> None:
        self.submit(self._start_route_impl(list(waypoints), float(speed_kmh), udid))

    def set_route_speed(self, speed_kmh: float) -> None:
        # Direct attribute write — read by the route loop every tick. Safe from
        # any thread because Python attribute writes on a single object are atomic.
        if speed_kmh > 0:
            self._route_speed_kmh = float(speed_kmh)

    def stop_route(self) -> None:
        self.submit(self._stop_route_impl())

    def clear(self) -> None:
        self.submit(self._clear_impl())

    # ---- async impls --------------------------------------------------

    async def _refresh_devices_impl(self) -> None:
        result: dict[str, DeviceInfo] = {}

        # USB-side (may be empty on machines without AMDS)
        try:
            usb = await list_usb_devices()
        except UsbmuxUnavailable:
            usb = []
        for d in usb:
            label_bits = [d.product_type or "iPhone", f"iOS {d.product_version}" if d.product_version else ""]
            if d.device_name:
                label_bits.append(f"({d.device_name})")
            label = "  ".join(s for s in label_bits if s).strip()
            result[d.udid] = DeviceInfo(udid=d.udid, label=label, connection="USB", tunneled=False)

        # Tunneled side (these are the ones DVT actually works on)
        try:
            rsds = await list_tunneled_devices()
        except Exception:
            rsds = []
        for rsd in rsds:
            existing = result.get(rsd.udid)
            label = f"iOS {rsd.product_version}" if rsd.product_version else "iOS device"
            if existing is None:
                result[rsd.udid] = DeviceInfo(udid=rsd.udid, label=label, connection="Tunneled", tunneled=True)
            else:
                existing.tunneled = True
                existing.connection = "USB+Tunneled" if existing.connection == "USB" else "Tunneled"
            try:
                await rsd.close()
            except Exception:
                pass

        self.devices_changed.emit(list(result.values()))

    async def _teleport_impl(self, latitude: float, longitude: float, udid: Optional[str]) -> None:
        # If a session is already running, just push the new coords through.
        if self._sim_cmd_queue is not None and self._sim_task is not None and not self._sim_task.done():
            await self._sim_cmd_queue.put(("set", latitude, longitude))
            self._current_state = SpoofState(udid=self._current_state.udid if self._current_state else (udid or ""),
                                             latitude=latitude, longitude=longitude)
            self.spoof_changed.emit(self._current_state)
            return

        # Else: start a fresh session.
        self.log_message.emit("Opening DVT session...")
        try:
            rsd = await get_tunneled_rsd(udid)
        except RuntimeError as exc:
            self.error.emit(str(exc))
            return

        self._sim_cmd_queue = asyncio.Queue()
        chosen_udid = rsd.udid
        self._current_state = SpoofState(udid=chosen_udid, latitude=latitude, longitude=longitude)
        self._sim_task = asyncio.create_task(self._sim_loop(rsd, latitude, longitude))
        self.spoof_changed.emit(self._current_state)

    async def _sim_loop(self, rsd, initial_lat: float, initial_lon: float) -> None:
        try:
            async with open_location_simulation(rsd) as sim:
                await sim.set(initial_lat, initial_lon)
                self.log_message.emit(f"Spoofing on {rsd.udid}")
                assert self._sim_cmd_queue is not None
                while True:
                    cmd = await self._sim_cmd_queue.get()
                    if cmd[0] == "stop":
                        try:
                            await sim.clear()
                        except Exception:
                            pass
                        break
                    if cmd[0] == "set":
                        _, lat, lon = cmd
                        await sim.set(lat, lon)
        except Exception as exc:
            logger.exception("DVT session crashed")
            self.error.emit(f"DVT session crashed: {exc}")
        finally:
            try:
                await rsd.close()
            except Exception:
                pass
            self._sim_task = None
            self._sim_cmd_queue = None
            self._current_state = None
            self.spoof_changed.emit(None)
            self.log_message.emit("Session closed.")

    async def _clear_impl(self) -> None:
        # First cancel any running route playback so it doesn't keep pushing
        # coords after the session is closed.
        await self._stop_route_impl()
        if self._sim_cmd_queue is None:
            return
        await self._sim_cmd_queue.put(("stop",))

    # ---- geocoding via Nominatim public demo --------------------------

    async def _geocode_impl(self, query: str) -> None:
        query = query.strip()
        if not query:
            self.geocode_results.emit([])
            return
        try:
            import urllib.parse
            import aiohttp  # already in pymobiledevice3 dep tree
        except ImportError:
            # Fall back to stdlib if aiohttp unavailable (run in default executor
            # so the loop stays responsive).
            await self._geocode_impl_stdlib(query)
            return

        url = (
            "https://nominatim.openstreetmap.org/search?"
            f"q={urllib.parse.quote(query)}&format=json&limit=5"
        )
        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": "poof-spoofer/0.1 (https://github.com/poof)"}
            ) as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        self.error.emit(f"Geocoding HTTP {resp.status}")
                        self.geocode_results.emit([])
                        return
                    data = await resp.json()
        except Exception as exc:
            self.error.emit(f"Geocoding failed: {exc}")
            self.geocode_results.emit([])
            return

        results = [
            GeocodeResult(
                name=item.get("display_name", "?"),
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
            )
            for item in data
            if "lat" in item and "lon" in item
        ]
        self.geocode_results.emit(results)
        self.log_message.emit(f'Search "{query}": {len(results)} result(s)')

    async def _geocode_impl_stdlib(self, query: str) -> None:
        """Pure-stdlib fallback when aiohttp isn't available."""
        import urllib.parse
        import urllib.request
        import json

        url = (
            "https://nominatim.openstreetmap.org/search?"
            f"q={urllib.parse.quote(query)}&format=json&limit=5"
        )
        loop = asyncio.get_running_loop()

        def _do_request() -> list:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "poof-spoofer/0.1 (https://github.com/poof)"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))

        try:
            data = await loop.run_in_executor(None, _do_request)
        except Exception as exc:
            self.error.emit(f"Geocoding failed: {exc}")
            self.geocode_results.emit([])
            return

        results = [
            GeocodeResult(
                name=item.get("display_name", "?"),
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
            )
            for item in data
            if "lat" in item and "lon" in item
        ]
        self.geocode_results.emit(results)
        self.log_message.emit(f'Search "{query}": {len(results)} result(s)')

    # ---- route playback ----------------------------------------------

    async def _start_route_impl(self, waypoints_data: list, speed_kmh: float, udid: Optional[str]) -> None:
        if len(waypoints_data) < 2:
            self.error.emit("Route needs at least two waypoints.")
            return
        if speed_kmh <= 0:
            self.error.emit("Speed must be > 0 km/h.")
            return

        # Stop any existing route first; keep the DVT session if it's open.
        await self._stop_route_impl()

        waypoints = [Waypoint(lat=float(p[0]), lon=float(p[1])) for p in waypoints_data]
        distance_km = total_distance_m(waypoints) / 1000.0
        self._route_speed_kmh = float(speed_kmh)
        eta_min = distance_km / self._route_speed_kmh * 60.0
        self.log_message.emit(
            f"Route: {len(waypoints)} waypoints, {distance_km:.2f} km, "
            f"ETA {eta_min:.1f} min @ {self._route_speed_kmh:.0f} km/h"
        )

        # Make sure a DVT session is running. If not, start one anchored at the
        # first waypoint (this is the same code path as a manual teleport).
        if self._sim_cmd_queue is None or self._sim_task is None or self._sim_task.done():
            await self._teleport_impl(waypoints[0].lat, waypoints[0].lon, udid)
            if self._sim_cmd_queue is None:
                return  # teleport failed; error already emitted

        self._route_task = asyncio.create_task(self._route_loop(waypoints))

    async def _route_loop(self, waypoints) -> None:
        try:
            assert self._sim_cmd_queue is not None
            # Re-read speed every tick so slider changes take effect live.
            speed_getter = lambda: self._route_speed_kmh
            async for pt in play_route(waypoints, speed_getter):
                await self._sim_cmd_queue.put(("set", pt.lat, pt.lon))
                if self._current_state is not None:
                    self._current_state = SpoofState(
                        udid=self._current_state.udid,
                        latitude=pt.lat,
                        longitude=pt.lon,
                    )
                    self.spoof_changed.emit(self._current_state)
            self.log_message.emit("Route finished.")
        except asyncio.CancelledError:
            self.log_message.emit("Route stopped.")
            raise
        except Exception as exc:
            logger.exception("Route playback crashed")
            self.error.emit(f"Route playback crashed: {exc}")
        finally:
            self._route_task = None

    async def _stop_route_impl(self) -> None:
        task = self._route_task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        self._route_task = None

    # ---- BLE PGP emulator --------------------------------------------

    async def _ble_start_impl(self) -> None:
        if self._ble_peripheral is not None:
            self.log_message.emit("BLE peripheral already running.")
            return
        try:
            master_key = ble_constants.load_master_key()
        except ble_constants.MasterKeyMissingError as exc:
            self.ble_state_changed.emit(f"error: master key missing")
            self.error.emit(str(exc))
            return
        try:
            peripheral = create_peripheral(master_key=master_key, cert=None)
        except PeripheralNotSupported as exc:
            self.ble_state_changed.emit(f"error: {exc}")
            self.error.emit(str(exc))
            return
        self.ble_state_changed.emit("starting")
        self.log_message.emit("Starting BLE peripheral...")
        try:
            await peripheral.start()
        except Exception as exc:
            self.ble_state_changed.emit(f"error: {exc}")
            self.error.emit(f"BLE peripheral start failed: {exc}")
            return
        self._ble_peripheral = peripheral
        self.ble_state_changed.emit("advertising")
        self.log_message.emit(
            f"BLE: advertising as '{ble_constants.DEVICE_NAME}'. "
            "iPhone can now find it under Settings -> Bluetooth."
        )

    async def _ble_stop_impl(self) -> None:
        if self._ble_peripheral is None:
            return
        try:
            await self._ble_peripheral.stop()
        except Exception:
            logger.exception("BLE peripheral stop failed")
        self._ble_peripheral = None
        self.ble_state_changed.emit("stopped")
        self.log_message.emit("BLE peripheral stopped.")

    async def _ble_generate_test_key_impl(self) -> None:
        import secrets
        path = ble_constants.MASTER_KEY_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(16))
        self.log_message.emit(
            f"Wrote placeholder PGP key to {path}. "
            "WARNING: not a real key — Pokemon GO server will reject. "
            "For testing BLE peripheral only."
        )


class SpoofSession(QObject):
    """Thread-safe singleton-ish facade. Construct once in main thread."""

    devices_changed = Signal(list)
    spoof_changed = Signal(object)
    geocode_results = Signal(list)
    ble_state_changed = Signal(str)
    error = Signal(str)
    log_message = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        # Re-emit worker signals on this object so widgets can connect to the facade.
        self._worker.devices_changed.connect(self.devices_changed)
        self._worker.spoof_changed.connect(self.spoof_changed)
        self._worker.geocode_results.connect(self.geocode_results)
        self._worker.ble_state_changed.connect(self.ble_state_changed)
        self._worker.error.connect(self.error)
        self._worker.log_message.connect(self.log_message)

        self._thread.start()
        # Block until the worker's asyncio loop is actually running, so callers
        # can safely submit coroutines immediately after construction.
        self._worker.wait_for_loop()

    def shutdown(self) -> None:
        """Call from main thread before app quits to cleanly stop the worker thread."""
        try:
            self._worker.clear()
        except Exception:
            pass
        self._worker.stop_loop()
        self._thread.quit()
        self._thread.wait(3000)

    # ---- proxied actions ---------------------------------------------

    def refresh_devices(self) -> None:
        self._worker.refresh_devices()

    def teleport(self, latitude: float, longitude: float, udid: Optional[str] = None) -> None:
        self._worker.teleport(latitude, longitude, udid)

    def geocode(self, query: str) -> None:
        self._worker.geocode(query)

    def ble_start(self) -> None:
        self._worker.ble_start()

    def ble_stop(self) -> None:
        self._worker.ble_stop()

    def ble_generate_test_key(self) -> None:
        self._worker.ble_generate_test_key()

    def current_spoof_position(self) -> Optional[tuple[float, float]]:
        """Convenience for the GUI to grab "where are we right now" without
        race conditions through signals."""
        st = self._worker._current_state
        if st is None:
            return None
        return (st.latitude, st.longitude)

    def start_route(self, waypoints: list, speed_kmh: float, udid: Optional[str] = None) -> None:
        self._worker.start_route(waypoints, speed_kmh, udid)

    def set_route_speed(self, speed_kmh: float) -> None:
        self._worker.set_route_speed(speed_kmh)

    def stop_route(self) -> None:
        self._worker.stop_route()

    def clear(self) -> None:
        self._worker.clear()
