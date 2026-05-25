"""Platform-dispatcher for the BLE peripheral transport.

Picks the right Layer-4 implementation at runtime:
  - Linux  -> transport_bluez.PgpBluezPeripheral (BlueZ via dbus-next)
  - Windows -> raises PeripheralNotSupported (WinRT impl deferred until a
               peripheral-capable BT adapter is available — see
               check_ble_peripheral.py)
  - macOS  -> not implemented (CoreBluetooth)
"""

from __future__ import annotations

import sys
from typing import Optional

from . import constants


class PeripheralNotSupported(RuntimeError):
    """The host's BT stack or hardware cannot host a BLE peripheral."""


def create_peripheral(master_key: bytes, cert: Optional[bytes] = None):
    """Return a started-able peripheral object for the current platform.

    On Linux this is a `PgpBluezPeripheral`. The returned object exposes the
    same lifecycle: `await peri.start()` / `await peri.stop()` and a `session`
    attribute (the underlying `PgpSession`).
    """
    if sys.platform == "linux":
        from .transport_bluez import PgpBluezPeripheral  # local import: dbus-next is Linux-only at runtime
        return PgpBluezPeripheral(master_key=master_key, cert=cert)

    if sys.platform == "win32":
        from .transport_winrt import PgpWinrtPeripheral
        return PgpWinrtPeripheral(master_key=master_key, cert=cert)

    raise PeripheralNotSupported(f"No peripheral transport for platform {sys.platform!r}.")


def describe_runtime_status() -> str:
    """Human-readable summary used by `cli_pgp status`."""
    lines = [
        "PGP BLE emulator - runtime status",
        f"  Platform:                   {sys.platform}",
        f"  Device name advertised:     {constants.DEVICE_NAME}",
        f"  Manufacturer name:          {constants.MANUFACTURER_NAME}",
        f"  Cert service UUID:          {constants.CERT_SERVICE_UUID}",
        f"  Main PGP service UUID:      {constants.PGP_SERVICE_UUID}",
        f"  Battery service UUID:       {constants.BATTERY_SERVICE_UUID}",
    ]
    if sys.platform == "linux":
        lines.append("  Transport:                  BlueZ via dbus-next")
    elif sys.platform == "win32":
        lines.append("  Transport:                  WinRT (requires peripheral-capable BT)")
    else:
        lines.append(f"  Transport:                  unsupported platform {sys.platform!r}")
    return "\n".join(lines)
