"""Route playback engine.

Plain linear / great-circle interpolation between waypoints at a configurable
speed. Doesn't follow road networks — that's planned realism polish for later.

Used by SpoofSession to drive the DVT/BLE coordinate stream over time.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Iterable, Optional, Union


EARTH_RADIUS_M = 6_371_008.8

# Default update rate: how often we push a new coordinate to DVT.
# 1 Hz matches what real GPS receivers do; higher rates may stress DVT/tunneld.
DEFAULT_UPDATE_HZ = 1.0


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float


def haversine_m(a: Waypoint, b: Waypoint) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def interpolate(a: Waypoint, b: Waypoint, t: float) -> Waypoint:
    """Linear interpolation along the great-circle for small t (sub-km segments).

    For our use case (~50 km radius per PROJECT.pdf MVP) the difference between
    a true slerp on the sphere and naive lat/lon linear interpolation is
    negligible (<1 m). Keep it simple.
    """
    t = max(0.0, min(1.0, t))
    return Waypoint(
        lat=a.lat + (b.lat - a.lat) * t,
        lon=a.lon + (b.lon - a.lon) * t,
    )


def total_distance_m(waypoints: list[Waypoint]) -> float:
    if len(waypoints) < 2:
        return 0.0
    return sum(haversine_m(waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1))


SpeedSource = Union[float, Callable[[], float]]


def _read_speed(src: SpeedSource) -> float:
    """Resolve a speed source (constant or callable) to a positive km/h value."""
    value = src() if callable(src) else src
    if value is None or value <= 0:
        raise ValueError("speed must be > 0 km/h")
    return float(value)


async def play_route(
    waypoints: Iterable[Waypoint],
    speed_kmh: SpeedSource,
    update_hz: float = DEFAULT_UPDATE_HZ,
    *,
    sleep: Optional[callable] = None,
) -> AsyncIterator[Waypoint]:
    """Yield (lat, lon) points along the polyline at the given ground speed.

    `speed_kmh` may be a constant float OR a zero-arg callable returning the
    current speed in km/h — the callable form is re-read on every tick so the
    speed can be adjusted live (e.g. from a UI slider) without restarting the
    playback.

    Yields the starting waypoint immediately, then advances by
    `current_speed * dt` metres per real second. Finishes by yielding the
    last waypoint exactly.

    Cancellation: cancelling the surrounding task stops playback cleanly.
    """
    if sleep is None:
        sleep = asyncio.sleep
    pts = list(waypoints)
    if len(pts) < 1:
        return
    if len(pts) == 1:
        yield pts[0]
        return
    # validate the initial speed; callable speed_source is re-read each tick.
    _read_speed(speed_kmh)
    if update_hz <= 0:
        raise ValueError("update_hz must be > 0")

    step_dt = 1.0 / update_hz

    yield pts[0]
    leg_idx = 0
    leg_progress_m = 0.0
    leg_len_m = haversine_m(pts[leg_idx], pts[leg_idx + 1])

    while leg_idx < len(pts) - 1:
        await sleep(step_dt)
        current_speed_kmh = _read_speed(speed_kmh)
        speed_mps = current_speed_kmh * 1000.0 / 3600.0
        leg_progress_m += speed_mps * step_dt

        # Possibly skip over short legs in one step.
        while leg_idx < len(pts) - 1 and leg_progress_m >= leg_len_m:
            leg_progress_m -= leg_len_m
            leg_idx += 1
            if leg_idx >= len(pts) - 1:
                break
            leg_len_m = haversine_m(pts[leg_idx], pts[leg_idx + 1])
            if leg_len_m == 0:
                continue  # zero-length leg (duplicate waypoint)

        if leg_idx >= len(pts) - 1:
            yield pts[-1]
            return

        t = leg_progress_m / leg_len_m if leg_len_m > 0 else 1.0
        yield interpolate(pts[leg_idx], pts[leg_idx + 1], t)

    yield pts[-1]
