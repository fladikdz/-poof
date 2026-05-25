"""Direct test of PgpWinrtPeripheral on the planshet — bypasses GUI/PyInstaller."""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from pathlib import Path

# Make ble.* importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(name)s  %(message)s")

from ble.transport_winrt import PgpWinrtPeripheral


async def main() -> int:
    master_key = bytes(16)  # placeholder zeros
    peri = PgpWinrtPeripheral(master_key=master_key)
    try:
        await peri.start()
    except Exception:
        print("=== START FAILED ===")
        traceback.print_exc()
        return 1

    print("Peripheral started. Holding for 60 seconds — check iPhone Bluetooth NOW.")
    await asyncio.sleep(60)
    print("Stopping...")
    try:
        await peri.stop()
    except Exception:
        traceback.print_exc()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
