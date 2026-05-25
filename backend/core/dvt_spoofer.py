from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


@asynccontextmanager
async def open_location_simulation(rsd: RemoteServiceDiscoveryService) -> AsyncIterator[LocationSimulation]:
    """Open a DVT session and yield a LocationSimulation handle.

    The simulated location persists only while this context is active — exiting it (or losing
    the tunneld connection) restores the real GPS reading on the device.
    """
    async with DvtProvider(rsd) as dvt, LocationSimulation(dvt) as location_simulation:
        yield location_simulation


async def set_location(rsd: RemoteServiceDiscoveryService, latitude: float, longitude: float) -> None:
    """One-shot helper used by the CLI inside a kept-alive session."""
    async with open_location_simulation(rsd) as sim:
        await sim.set(latitude, longitude)


async def clear_location(rsd: RemoteServiceDiscoveryService) -> None:
    async with open_location_simulation(rsd) as sim:
        await sim.clear()
