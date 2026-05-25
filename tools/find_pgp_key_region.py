"""Find candidate AES master keys in the gap between AES constants in
WinBLEPeripheral.dll.

Strategy: locate AES S-box, inv S-box, Rcon, AES-NI shuffle masks. The
master key constant is almost certainly a 16-byte high-entropy value sitting
in the same .rdata region but NOT inside these well-known tables.
"""

from __future__ import annotations

import sys
from collections import Counter
from math import log2
from pathlib import Path


AES_SBOX = bytes([
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
])

AES_INV_SBOX_PREFIX = bytes([0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36])
AES_RCON_PREFIX = bytes([0x8d, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36])


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum((c / total) * log2(c / total) for c in counts.values())


def is_ascii_text(blob: bytes) -> bool:
    printable = sum(1 for b in blob if (0x20 <= b <= 0x7e) or b in (0x00, 0x09, 0x0a, 0x0d))
    return printable >= len(blob) - 2


def is_utf16le_text(blob: bytes) -> bool:
    if len(blob) < 4:
        return False
    return all(blob[i + 1] == 0 for i in range(0, len(blob) - 1, 2))


def is_low_entropy(blob: bytes) -> bool:
    unique = len(set(blob))
    if unique < 8:
        return True
    # long runs of same byte
    for i in range(len(blob) - 3):
        if blob[i] == blob[i + 1] == blob[i + 2] == blob[i + 3]:
            return True
    return False


def is_aesni_shuffle_pattern(blob: bytes) -> bool:
    """AES-NI shuffle masks have a typical layout: monotonic low-nibble bytes
    (00-0f) with some constant 0xff or 0x80 sprinkled. They look unlike a
    random AES key."""
    # Count bytes in [0..0x0f]
    low = sum(1 for b in blob if b <= 0x0f)
    return low >= 12  # mostly low-nibble values


def main() -> None:
    pe_path = Path(sys.argv[1])
    data = pe_path.read_bytes()

    sbox_off = data.find(AES_SBOX)
    invsbox_off = data.find(AES_INV_SBOX_PREFIX)
    rcon_off = data.find(AES_RCON_PREFIX)

    print(f"AES S-box (forward):  0x{sbox_off:08x}")
    print(f"AES S-box (inverse):  0x{invsbox_off:08x}")
    print(f"AES Rcon prefix:      0x{rcon_off:08x}")

    # Region of interest: from after Rcon end (~0x70d60) to start of AES-NI masks (0x7168a).
    region_start = rcon_off + 16 if rcon_off >= 0 else 0x70d70
    region_end = 0x71700  # approximate start of AES-NI shuffle masks
    print(f"\nScanning region 0x{region_start:08x}..0x{region_end:08x} "
          f"({region_end - region_start} bytes)")

    candidates = []
    # Slide a 16-byte window with 1-byte step (not just 16-aligned)
    for off in range(region_start, region_end - 16):
        blob = data[off:off + 16]
        if blob == b"\x00" * 16 or blob == b"\xff" * 16:
            continue
        if is_ascii_text(blob) or is_utf16le_text(blob):
            continue
        if is_low_entropy(blob):
            continue
        if is_aesni_shuffle_pattern(blob):
            continue
        ent = entropy(blob)
        if ent < 3.5:
            continue
        candidates.append((off, blob, ent))

    # Cluster: skip overlapping windows
    clustered = []
    last_off = -100
    for off, blob, ent in candidates:
        if off - last_off >= 16:
            clustered.append((off, blob, ent))
            last_off = off

    print(f"\n{len(clustered)} high-entropy 16-byte blob candidates:\n")
    for off, blob, ent in clustered:
        rel = off - sbox_off
        print(f"  0x{off:08x} (S-box{rel:+d})  ent={ent:.2f}  {blob.hex()}")


if __name__ == "__main__":
    main()
