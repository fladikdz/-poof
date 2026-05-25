"""Try several BluetoothLEAdvertisementPublisher variants to find one that
doesn't fail with INVALIDARG and actually broadcasts a local_name iPhone can see."""

from __future__ import annotations

import asyncio
import traceback

from winsdk.windows.devices.bluetooth.advertisement import (
    BluetoothLEAdvertisement,
    BluetoothLEAdvertisementPublisher,
    BluetoothLEManufacturerData,
)
from winsdk.windows.storage.streams import DataWriter


def make_buffer(data: bytes):
    w = DataWriter()
    w.write_bytes(data)
    return w.detach_buffer()


def try_variant(label: str, build) -> None:
    print(f"\n=== {label} ===")
    try:
        publisher = build()
        publisher.start()
        print(f"  start() OK, status: {publisher.status}")
        import time
        time.sleep(2)
        publisher.stop()
        print(f"  stopped OK")
    except OSError as e:
        # Strip non-ASCII (Russian error text from Windows) before printing —
        # otherwise crashes on cp1250 stdout.
        msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  FAILED: OSError winerror={getattr(e, 'winerror', '?')} msg='{msg}'")
    except Exception as e:
        msg = str(e).encode("ascii", "replace").decode("ascii")
        print(f"  FAILED: {type(e).__name__}: {msg}")


def v1_empty_ctor():
    p = BluetoothLEAdvertisementPublisher()
    p.advertisement.local_name = "Pokemon GO Plus"
    return p


def v2_short_name_in_ctor():
    adv = BluetoothLEAdvertisement()
    adv.local_name = "PGP"
    return BluetoothLEAdvertisementPublisher(adv)


def v3_manufacturer_data_only():
    adv = BluetoothLEAdvertisement()
    md = BluetoothLEManufacturerData()
    md.company_id = 0x004C  # Apple
    md.data = make_buffer(b"\x01\x02\x03")
    adv.manufacturer_data.append(md)
    return BluetoothLEAdvertisementPublisher(adv)


def v4_name_plus_manufdata():
    adv = BluetoothLEAdvertisement()
    adv.local_name = "PGP"
    md = BluetoothLEManufacturerData()
    md.company_id = 0xFFFF
    md.data = make_buffer(b"\x42")
    adv.manufacturer_data.append(md)
    return BluetoothLEAdvertisementPublisher(adv)


def v5_long_name_via_empty_ctor():
    p = BluetoothLEAdvertisementPublisher()
    p.advertisement.local_name = "Pokemon GO Plus"  # 15 chars
    return p


def v6_simple_long_name_in_ctor():
    adv = BluetoothLEAdvertisement()
    adv.local_name = "Pokemon GO Plus"
    return BluetoothLEAdvertisementPublisher(adv)


def v7_no_data_at_all():
    return BluetoothLEAdvertisementPublisher()


if __name__ == "__main__":
    try_variant("v1: empty ctor, then set local_name = 'Pokemon GO Plus'", v1_empty_ctor)
    try_variant("v2: short 'PGP' via ctor adv", v2_short_name_in_ctor)
    try_variant("v3: manufacturer data only (Apple 0x004C)", v3_manufacturer_data_only)
    try_variant("v4: short name + manuf data", v4_name_plus_manufdata)
    try_variant("v5: empty ctor + long name", v5_long_name_via_empty_ctor)
    try_variant("v6: long name via ctor adv", v6_simple_long_name_in_ctor)
    try_variant("v7: completely empty advertisement", v7_no_data_at_all)
