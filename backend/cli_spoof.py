"""Minimal CLI for iOS Location Spoofer (Iteration 1+2 merged: iOS 17+ via tunneld).

Usage:
    python cli_spoof.py devices
    python cli_spoof.py spoof --lat 52.2297 --lon 21.0122 [--udid UDID]
    python cli_spoof.py clear [--udid UDID]

Requires `pymobiledevice3 remote tunneld` running with admin/sudo privileges.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import click

from core.dvt_spoofer import open_location_simulation
from core.ios_manager import (
    UsbmuxUnavailable,
    get_tunneled_rsd,
    list_tunneled_devices,
    list_usb_devices,
)
from core.movement import Waypoint, play_route, total_distance_m


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


@click.group()
def cli() -> None:
    """iOS Location Spoofer — minimal DVT CLI."""


@cli.command("devices")
def cmd_devices() -> None:
    """List USB-connected iPhones and those reachable via tunneld (ready for DVT)."""
    _run(_list_devices_impl())


async def _list_devices_impl() -> None:
    click.echo("=== USB devices (usbmuxd) ===")
    try:
        usb = await list_usb_devices()
    except UsbmuxUnavailable as exc:
        click.echo(f"  unavailable: {exc}")
    else:
        if not usb:
            click.echo("  (none)")
        for d in usb:
            line = f"  {d.udid}  type={d.connection_type}"
            if d.product_type or d.product_version:
                line += f"  {d.product_type or '?'} iOS {d.product_version or '?'}"
            if d.device_name:
                line += f"  '{d.device_name}'"
            click.echo(line)

    click.echo("\n=== Tunneled devices (ready for DVT on iOS 17+) ===")
    try:
        rsds = await list_tunneled_devices()
    except Exception as exc:
        msg = str(exc) or exc.__class__.__name__
        click.echo(f"  tunneld unreachable: {msg}")
        click.echo("  Start it with: pymobiledevice3 remote tunneld   (needs admin)")
        return
    if not rsds:
        click.echo("  (none — run `pymobiledevice3 remote tunneld` as admin)")
    for rsd in rsds:
        click.echo(f"  {rsd.udid}  iOS {rsd.product_version}  rsd={rsd.service.address}")
        await rsd.close()


@cli.command("spoof")
@click.option("--lat", "latitude", type=float, required=True, help="Target latitude (decimal degrees).")
@click.option("--lon", "longitude", type=float, required=True, help="Target longitude (decimal degrees).")
@click.option("--udid", type=str, default=None, help="Specific device UDID (defaults to first tunneled device).")
def cmd_spoof(latitude: float, longitude: float, udid: Optional[str]) -> None:
    """Spoof location and hold the DVT session open until Ctrl+C.

    Important: iOS reverts to real GPS the moment this process exits.
    """
    _run(_spoof_impl(latitude, longitude, udid))


async def _spoof_impl(latitude: float, longitude: float, udid: Optional[str]) -> None:
    rsd = await get_tunneled_rsd(udid)
    try:
        async with open_location_simulation(rsd) as sim:
            await sim.set(latitude, longitude)
            click.echo(f"Spoofing location on {rsd.udid} (iOS {rsd.product_version})")
            click.echo(f"  lat={latitude}  lon={longitude}")
            click.echo("Press Ctrl+C to release the simulation and restore real GPS.")
            await asyncio.Event().wait()
    finally:
        await rsd.close()


@cli.command("clear")
@click.option("--udid", type=str, default=None, help="Specific device UDID (defaults to first tunneled device).")
def cmd_clear(udid: Optional[str]) -> None:
    """Explicitly clear an active simulation on a device."""
    _run(_clear_impl(udid))


async def _clear_impl(udid: Optional[str]) -> None:
    rsd = await get_tunneled_rsd(udid)
    try:
        async with open_location_simulation(rsd) as sim:
            await sim.clear()
        click.echo(f"Cleared simulation on {rsd.udid}.")
    finally:
        await rsd.close()


@cli.command("route")
@click.option(
    "--point",
    "points",
    type=str,
    multiple=True,
    required=True,
    help="Waypoint as 'LAT,LON'. Repeat for each. Minimum 2.",
)
@click.option("--speed", "speed_kmh", type=float, default=40.0, show_default=True,
              help="Ground speed in km/h.")
@click.option("--udid", type=str, default=None, help="Specific device UDID.")
def cmd_route(points: tuple[str, ...], speed_kmh: float, udid: Optional[str]) -> None:
    """Play a route through N waypoints at a fixed speed, holding DVT open.

    Example:
        cli_spoof route --point 52.2297,21.0122 --point 52.2495,21.0177 --speed 50
    """
    waypoints: list[Waypoint] = []
    for raw in points:
        try:
            lat_s, lon_s = raw.split(",", 1)
            waypoints.append(Waypoint(lat=float(lat_s), lon=float(lon_s)))
        except (ValueError, AttributeError):
            click.echo(f"Invalid --point value {raw!r}; expected 'LAT,LON'.", err=True)
            sys.exit(2)
    if len(waypoints) < 2:
        click.echo("Need at least two --point values.", err=True)
        sys.exit(2)
    _run(_route_impl(waypoints, speed_kmh, udid))


async def _route_impl(waypoints: list, speed_kmh: float, udid: Optional[str]) -> None:
    rsd = await get_tunneled_rsd(udid)
    try:
        distance_km = total_distance_m(waypoints) / 1000.0
        eta_min = distance_km / speed_kmh * 60.0
        click.echo(
            f"Route on {rsd.udid} (iOS {rsd.product_version}): "
            f"{len(waypoints)} waypoints, {distance_km:.2f} km, ETA {eta_min:.1f} min @ {speed_kmh:.0f} km/h"
        )
        async with open_location_simulation(rsd) as sim:
            await sim.set(waypoints[0].lat, waypoints[0].lon)
            click.echo("Press Ctrl+C to abort.")
            async for pt in play_route(waypoints, speed_kmh):
                await sim.set(pt.lat, pt.lon)
            click.echo("Route finished. iOS reverts to real GPS now.")
    finally:
        await rsd.close()


if __name__ == "__main__":
    cli()
