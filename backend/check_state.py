"""Quick diagnostic: is the iPhone visible and is Developer Mode enabled?"""

from __future__ import annotations

import asyncio
import socket

import requests

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.usbmux import list_devices


async def main() -> None:
    print("--- USB ---")
    muxes = await list_devices()
    if not muxes:
        print("  no devices on USB")
        return
    mux = muxes[0]
    print(f"  serial={mux.serial}  type={mux.connection_type}")

    lockdown = await create_using_usbmux(serial=mux.serial, autopair=False)
    try:
        print(f"  product={lockdown.product_type}  iOS={lockdown.product_version}")
        try:
            dm = await lockdown.get_developer_mode_status()
            print(f"  DeveloperMode enabled: {dm}")
        except Exception as exc:
            print(f"  DeveloperMode query failed: {exc}")
    finally:
        await lockdown.close()

    print("--- tunneld (127.0.0.1:49151) ---")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(("127.0.0.1", 49151))
        print("  TCP port open")
        sock.close()
        try:
            resp = requests.get("http://127.0.0.1:49151/", timeout=2)
            tunnels = resp.json()
            print(f"  tunnels: {tunnels}")
        except Exception as exc:
            print(f"  HTTP query failed: {exc}")
    except OSError as exc:
        print(f"  not running ({exc})")


if __name__ == "__main__":
    asyncio.run(main())
