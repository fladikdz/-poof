"""AES-CTR / AES-ECB primitives used in the PGP handshake.

The PGP authentication protocol uses AES-128. Two operations are needed at the
emulator side:
  - encrypt/decrypt a single 16-byte block with a known key (used for both the
    cert-derivation step and the per-session nonce blinding)
  - process longer payloads in CTR mode with a fixed counter base

All functions here are pure — no state, no network, no BT. They are the most
testable layer of the BLE work and the place where pgpemu test vectors plug in.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# ----- single-block helpers ----------------------------------------------

def aes_ecb_encrypt(key: bytes, block: bytes) -> bytes:
    """One-block AES-ECB encrypt. key and block must each be 16 bytes."""
    if len(key) != 16:
        raise ValueError(f"AES-128 key must be 16 bytes, got {len(key)}")
    if len(block) != 16:
        raise ValueError(f"AES block must be 16 bytes, got {len(block)}")
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(block) + enc.finalize()


def aes_ecb_decrypt(key: bytes, block: bytes) -> bytes:
    """One-block AES-ECB decrypt."""
    if len(key) != 16:
        raise ValueError(f"AES-128 key must be 16 bytes, got {len(key)}")
    if len(block) != 16:
        raise ValueError(f"AES block must be 16 bytes, got {len(block)}")
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return dec.update(block) + dec.finalize()


# ----- CTR-mode helpers ---------------------------------------------------

def aes_ctr_apply(key: bytes, nonce16: bytes, data: bytes) -> bytes:
    """AES-CTR encrypt/decrypt (symmetric). nonce16 is the full 16-byte counter base."""
    if len(key) != 16:
        raise ValueError(f"AES-128 key must be 16 bytes, got {len(key)}")
    if len(nonce16) != 16:
        raise ValueError(f"CTR counter base must be 16 bytes, got {len(nonce16)}")
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce16))
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


# ----- handshake primitives ----------------------------------------------

def random_nonce(size: int = 16) -> bytes:
    """Cryptographically strong random bytes for challenge generation."""
    return os.urandom(size)


def xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two equal-length byte strings."""
    if len(a) != len(b):
        raise ValueError(f"xor lengths differ: {len(a)} vs {len(b)}")
    return bytes(x ^ y for x, y in zip(a, b))


def derive_session_key(master_key: bytes, central_nonce: bytes, pgp_nonce: bytes) -> bytes:
    """Per-session AES key derived from the two nonces and the master key.

    This follows the documented PGP pattern: take both nonces (each 16 bytes),
    XOR-combine them, then encrypt with the master key. The result is the AES key
    used for subsequent CTR-mode encrypted exchanges in the same session.

    Note: this is the *general* pattern. The exact concatenation/order used by
    real PGP vs pgpemu vs AnyTo may differ — verify against pgpemu source
    when bringing this into integration testing.
    """
    if len(central_nonce) != 16 or len(pgp_nonce) != 16:
        raise ValueError("both nonces must be 16 bytes")
    combined = xor_bytes(central_nonce, pgp_nonce)
    return aes_ecb_encrypt(master_key, combined)
