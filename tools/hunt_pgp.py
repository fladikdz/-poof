"""Targeted hunt for PGP/AES-related artifacts in a DLL.

Looks for:
- Functions/strings containing PGP keywords (pokemon, sfida, plus, cert, etc.)
- Function symbol names suggesting crypto operations
- Hardcoded hex blobs that could be AES keys (32 hex chars = 16-byte key, 64 = 32-byte)
- References to libsodium functions
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pefile

PGP_KEYWORDS = [
    b"pokemon", b"PokeMon", b"PokeBall", b"Pokeball", b"GoPlus", b"GO_Plus", b"PGP",
    b"Sfida", b"sfida", b"SFIDA",
    b"Niantic", b"niantic", b"NIANTIC",
    b"AES", b"aes_ctr", b"aes_encrypt", b"aes_decrypt",
    b"crypto_secretbox", b"crypto_stream",
    b"reconnect", b"first_pair", b"first-pair",
    b"cert_key", b"certificate_key", b"pgp_cert", b"pgp_key",
    b"sodium", b"libsodium",
    b"MAC_addr", b"mac_address", b"bt_address",
    b"setSecurityKey", b"GenerateCert", b"GeneratePGPCert",
    b"AdvName", b"DeviceName", b"Pokemon GO Plus",
    b"GattService", b"GattLocalCharacteristic", b"AdvertisementPublisher",
    b"StartBLEService", b"WinBLEPeripheral",
]


def extract_strings(data: bytes, min_len: int = 4) -> list[str]:
    out = []
    seen: set[str] = set()
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        s = m.group().decode("ascii", errors="ignore")
        if s not in seen:
            seen.add(s)
            out.append(s)
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
    print(f"=== {pe_path.name} ({pe_path.stat().st_size:,} bytes) ===\n")

    data = pe_path.read_bytes()
    all_strings = extract_strings(data, min_len=4)

    # 1. Keyword matches in strings
    print("--- Keyword matches (case-insensitive) ---")
    for kw in PGP_KEYWORDS:
        kw_l = kw.lower()
        hits = [s for s in all_strings if kw_l in s.lower().encode("ascii", errors="ignore")]
        if hits:
            print(f"  [{kw.decode()}] ({len(hits)} hits)")
            for h in hits[:8]:
                print(f"    {h[:200]}")
            if len(hits) > 8:
                print(f"    ... +{len(hits) - 8} more")

    # 2. Hex blobs that could be AES keys: long runs of hex characters in strings
    print("\n--- Suspicious hex blobs (potential keys) ---")
    hex_re = re.compile(r"^[0-9a-fA-F]+$")
    hex_blobs = [s for s in all_strings if 24 <= len(s) <= 256 and hex_re.match(s)]
    if hex_blobs:
        for blob in hex_blobs[:30]:
            print(f"  len={len(blob):3d}  {blob[:80]}{'...' if len(blob) > 80 else ''}")
    else:
        print("  none in plain strings")

    # 3. Function imports / exports hinting at crypto/BLE
    print("\n--- Crypto/BLE-flavoured imports ---")
    pe = pefile.PE(str(pe_path), fast_load=False)
    crypto_kws = ("aes_", "crypto_", "sodium_", "RSA", "EVP_", "ssl_", "TLS_",
                  "Bluetooth", "Gatt", "Advertisement", "BLE", "RoGet")
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            crypto_funcs = []
            for imp in entry.imports:
                name = imp.name.decode() if imp.name else ""
                if any(kw.lower() in name.lower() for kw in crypto_kws):
                    crypto_funcs.append(name)
            if crypto_funcs:
                print(f"  from {entry.dll.decode()}:")
                for f in crypto_funcs[:30]:
                    print(f"    {f}")
                if len(crypto_funcs) > 30:
                    print(f"    ... +{len(crypto_funcs) - 30} more")

    # 4. PDB path leak (developer slipup)
    print("\n--- Source/PDB path leaks ---")
    pdb_re = re.compile(r"[A-Za-z]:\\[^\x00\s]+\\[A-Za-z0-9_]+\.(pdb|cpp|h)$")
    leaked = [s for s in all_strings if pdb_re.search(s) or s.endswith(".pdb")]
    for s in leaked[:20]:
        print(f"  {s}")


if __name__ == "__main__":
    main()
