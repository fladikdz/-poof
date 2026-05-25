"""PE-inspection: imports/exports + interesting strings from a DLL/EXE.

Usage: python inspect_dll.py <path-to-pe-file>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pefile

GUID_RE = re.compile(rb"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
INTERESTING_KEYWORDS = [
    b"GATT", b"BLE", b"Bluetooth", b"Peripheral", b"Advertise", b"Advertis",
    b"Pokemon", b"PokeMon", b"PokeBall", b"Pokeball", b"PGP", b"Plus",
    b"Adventure", b"Gotcha", b"AdvMode", b"AdvName",
    b"GoPlus", b"PokemonGoPlus", b"PokemonGOPlus",
    b"Niantic", b"PokeManager",
    b"Characteristic", b"Service", b"UUID",
    b"AES", b"CTR", b"Cert", b"Key",
    b"ExternalAccessory", b"MFi", b"ExternalGPS",
    b"NMEA", b"GPS",
]


def extract_strings(data: bytes, min_len: int = 5) -> list[str]:
    """ASCII + UTF-16LE strings, deduped, preserving order of first appearance."""
    out: list[str] = []
    seen: set[str] = set()
    # ASCII
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        s = m.group().decode("ascii", errors="ignore")
        if s not in seen:
            seen.add(s)
            out.append(s)
    # UTF-16LE
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){%d,}" % min_len, data):
        try:
            s = m.group().decode("utf-16-le", errors="ignore").rstrip("\x00")
        except UnicodeDecodeError:
            continue
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def main() -> None:
    pe_path = Path(sys.argv[1])
    pe = pefile.PE(str(pe_path), fast_load=False)
    data = pe_path.read_bytes()

    print(f"=== {pe_path.name} ({pe_path.stat().st_size} bytes) ===")
    print(f"Machine: 0x{pe.FILE_HEADER.Machine:04x}")
    print(f"TimeDateStamp: {pe.FILE_HEADER.TimeDateStamp}")

    # GUIDs (potential service / characteristic UUIDs)
    guids = sorted(set(m.group().decode("ascii") for m in GUID_RE.finditer(data)))
    print(f"\n--- GUIDs (raw, {len(guids)}) ---")
    for g in guids:
        print(f"  {g}")

    # Imports
    print("\n--- Imports ---")
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            funcs = [
                (imp.name.decode() if imp.name else f"ord{imp.ordinal}")
                for imp in entry.imports
            ]
            print(f"  {entry.dll.decode()}: {len(funcs)} funcs")
            ble_relevant = [f for f in funcs if any(k.lower() in f.lower() for k in [
                "bluetooth", "ble", "gatt", "advertis", "winrt", "rocreate", "rogetactivation",
            ])]
            if ble_relevant:
                for f in ble_relevant:
                    print(f"      ! {f}")

    # Exports
    print("\n--- Exports ---")
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            name = exp.name.decode() if exp.name else f"ord{exp.ordinal}"
            print(f"  {name}")

    # Interesting strings
    print("\n--- Interesting strings ---")
    all_strings = extract_strings(data, min_len=4)
    matches: dict[str, list[str]] = {}
    for s in all_strings:
        sl = s.encode("ascii", errors="ignore").lower()
        for kw in INTERESTING_KEYWORDS:
            if kw.lower() in sl:
                matches.setdefault(kw.decode(), []).append(s)
                break
    for kw, hits in matches.items():
        print(f"  [{kw}]")
        for h in hits[:25]:
            print(f"    {h}")
        if len(hits) > 25:
            print(f"    ... +{len(hits) - 25} more")

    # All-strings summary
    print(f"\n--- Total strings: {len(all_strings)} ---")


if __name__ == "__main__":
    main()
