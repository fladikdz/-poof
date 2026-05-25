"""Enumerate ALL Bluetooth adapters on this PC and report peripheral-role support.

Plug in candidate USB BT dongles before running. Each adapter is listed separately
so you can tell which one supports peripheral role (the requirement for PGP emulation).
"""

from __future__ import annotations

import asyncio
import sys

from winsdk.windows.devices.bluetooth import BluetoothAdapter
from winsdk.windows.devices.enumeration import DeviceInformation
from winsdk.windows.devices.radios import RadioState


def fmt_mac(addr: int) -> str:
    h = f"{addr:012X}"
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))


async def main() -> int:
    selector = BluetoothAdapter.get_device_selector()
    # winsdk overload disambiguation: pass extra empty list to bind the
    # (aqsFilter, additionalProperties) overload instead of (deviceClass) which expects an int.
    devices = await DeviceInformation.find_all_async(selector, [])

    print(f"Found {len(devices)} Bluetooth adapter(s).\n")
    if not devices:
        print("No BT adapters detected. Plug one in and re-run.")
        return 1

    any_peripheral = False
    for idx, devinfo in enumerate(devices, 1):
        print(f"--- Adapter #{idx} ---")
        print(f"  Name:    {devinfo.name}")
        print(f"  Id:      {devinfo.id}")
        print(f"  Enabled: {devinfo.is_enabled}")
        try:
            adapter = await BluetoothAdapter.from_id_async(devinfo.id)
        except Exception as exc:
            print(f"  (failed to open: {exc})")
            continue
        if adapter is None:
            print("  (BluetoothAdapter.from_id_async returned None)")
            continue

        peripheral = adapter.is_peripheral_role_supported
        any_peripheral = any_peripheral or peripheral
        marker = "  <<< YES, USE THIS" if peripheral else ""
        print(f"  MAC:                 {fmt_mac(adapter.bluetooth_address)}")
        print(f"  Classic BT:          {adapter.is_classic_supported}")
        print(f"  BLE:                 {adapter.is_low_energy_supported}")
        print(f"  Central role:        {adapter.is_central_role_supported}")
        print(f"  Peripheral role:     {peripheral}{marker}")
        print(f"  Adv. offload:        {adapter.is_advertisement_offload_supported}")
        print(f"  Extended adv.:       {adapter.is_extended_advertising_supported}")

        try:
            radio = await adapter.get_radio_async()
            if radio is not None:
                print(f"  Radio:               {radio.name}  state={radio.state.name}")
                if radio.state != RadioState.ON:
                    print("  WARNING: radio not ON; toggle BT on or check device manager.")
        except Exception as exc:
            print(f"  Radio query failed: {exc}")
        print()

    if any_peripheral:
        print("OK: at least one adapter supports peripheral role. Iteration 5 can proceed on it.")
        rc = 0
    else:
        print("!! None of the present adapters support peripheral role.")
        print("   Candidates that usually work: CSR8510-based dongles (~$5-10),")
        print("   modern BT 5.0 dongles with RTL8761B chip (TP-Link UB500, Asus BT500).")
        rc = 2
    # Keep window open when launched via double-click (so the user can read).
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
