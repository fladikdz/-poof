"""Bypass for the typer/rich CLI which spews XTGETTCAP escape codes in Windows
PowerShell legacy console. Calls AmfiService.reveal_developer_mode_option_in_ui()
directly — clean stdout, real exception if it fails.

Run from an Administrator PowerShell so AMDS can write the pair record to
C:\\ProgramData\\Apple\\Lockdown on first pairing.
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.amfi import AmfiService
from pymobiledevice3.usbmux import list_devices


async def main() -> int:
    muxes = await list_devices()
    if not muxes:
        print("ERROR: no iPhone detected over USB. Plug it in and trust the computer.")
        return 1

    mux = muxes[0]
    print(f"Target: serial={mux.serial}  connection={mux.connection_type}")

    print("Opening lockdown (autopair=True) ...")
    lockdown = await create_using_usbmux(serial=mux.serial, autopair=True)
    try:
        print(f"Paired OK. iOS {lockdown.product_version}  product={lockdown.product_type}")
        amfi = AmfiService(lockdown)
        print("Sending DEVELOPER_MODE_REVEAL ...")
        await amfi.reveal_developer_mode_option_in_ui()
        print("OK. Developer Mode toggle should now appear under Settings -> Privacy & Security.")
    finally:
        await lockdown.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        traceback.print_exc()
        sys.exit(2)
