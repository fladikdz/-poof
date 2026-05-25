from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pymobiledevice3.exceptions import ConnectionFailedToUsbmuxdError, TunneldConnectionError
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.tunneld.api import (
    TUNNELD_DEFAULT_ADDRESS,
    get_tunneld_device_by_udid,
    get_tunneld_devices,
)
from pymobiledevice3.usbmux import list_devices


class UsbmuxUnavailable(RuntimeError):
    """usbmuxd / Apple Mobile Device Service is not running or not installed."""


@dataclass
class UsbDevice:
    udid: str
    connection_type: str
    serial: Optional[str] = None
    product_type: Optional[str] = None
    product_version: Optional[str] = None
    device_name: Optional[str] = None


async def list_usb_devices() -> list[UsbDevice]:
    """Enumerate iPhones visible to usbmuxd. Lockdown query fills in human-readable fields.

    Raises UsbmuxUnavailable if the usbmuxd socket is unreachable (no AMDS on Windows, etc).
    """
    result: list[UsbDevice] = []
    try:
        muxes = await list_devices()
    except ConnectionFailedToUsbmuxdError as exc:
        raise UsbmuxUnavailable(
            "usbmuxd is not reachable. On Windows install Apple Mobile Device Support "
            "(comes with iTunes / Apple Devices app). Tunneld-based DVT still works without it."
        ) from exc
    for mux in muxes:
        info = UsbDevice(udid=mux.serial, connection_type=mux.connection_type, serial=mux.serial)
        try:
            lockdown = await create_using_usbmux(serial=mux.serial, autopair=False)
            try:
                info.product_type = lockdown.product_type
                info.product_version = lockdown.product_version
                info.device_name = lockdown.all_values.get("DeviceName")
            finally:
                await lockdown.close()
        except Exception:
            # Trust not established or transient — still report the device as detected.
            pass
        result.append(info)
    return result


async def list_tunneled_devices() -> list[RemoteServiceDiscoveryService]:
    """Devices currently exposed via a running tunneld instance (required for iOS 17+ DVT)."""
    return await get_tunneld_devices()


async def get_tunneled_rsd(udid: Optional[str] = None) -> RemoteServiceDiscoveryService:
    """Return an RSD for the chosen UDID (or the first available device).

    Raises RuntimeError with a user-friendly message if tunneld isn't running or no device matches.
    """
    try:
        if udid is not None:
            rsd = await get_tunneld_device_by_udid(udid)
            if rsd is None:
                raise RuntimeError(f"No tunneled device with UDID {udid}. Is the device paired and tunneld running?")
            return rsd
        rsds = await get_tunneld_devices()
        if not rsds:
            raise RuntimeError(
                "No tunneled devices found. Start tunneld first:\n"
                "  pymobiledevice3 remote tunneld   (run as Administrator on Windows / sudo on Linux/macOS)"
            )
        return rsds[0]
    except TunneldConnectionError as exc:
        raise RuntimeError(
            f"tunneld is not reachable at {TUNNELD_DEFAULT_ADDRESS[0]}:{TUNNELD_DEFAULT_ADDRESS[1]}.\n"
            "Start it with: pymobiledevice3 remote tunneld  (needs admin/sudo)"
        ) from exc
