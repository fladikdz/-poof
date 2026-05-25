"""Crypto layer tests — verify the primitives independent of any BT or protocol.

When pgpemu test vectors are available, swap the made-up keys/blocks here for
known good ones for real validation.
"""

from __future__ import annotations

import pytest

from backend.ble.crypto import (
    aes_ctr_apply,
    aes_ecb_decrypt,
    aes_ecb_encrypt,
    derive_session_key,
    random_nonce,
    xor_bytes,
)

# NIST FIPS-197 AES-128 ECB test vector (Appendix C.1)
NIST_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
NIST_PT  = bytes.fromhex("00112233445566778899aabbccddeeff")
NIST_CT  = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")


def test_aes_ecb_encrypt_matches_nist_vector():
    assert aes_ecb_encrypt(NIST_KEY, NIST_PT) == NIST_CT


def test_aes_ecb_decrypt_matches_nist_vector():
    assert aes_ecb_decrypt(NIST_KEY, NIST_CT) == NIST_PT


def test_aes_ecb_encrypt_rejects_short_key():
    with pytest.raises(ValueError, match="16 bytes"):
        aes_ecb_encrypt(b"shortkey", b"\x00" * 16)


def test_aes_ecb_encrypt_rejects_short_block():
    with pytest.raises(ValueError, match="16 bytes"):
        aes_ecb_encrypt(b"\x00" * 16, b"short")


def test_aes_ctr_symmetric():
    key = b"\x11" * 16
    nonce = b"\x22" * 16
    pt = b"hello world, this is a test payload spanning many AES blocks!!!!"
    ct = aes_ctr_apply(key, nonce, pt)
    assert ct != pt  # actually encrypted
    assert aes_ctr_apply(key, nonce, ct) == pt  # symmetric


def test_aes_ctr_rejects_bad_nonce():
    with pytest.raises(ValueError, match="16 bytes"):
        aes_ctr_apply(b"\x00" * 16, b"short", b"data")


def test_random_nonce_default_is_16_bytes():
    n = random_nonce()
    assert isinstance(n, bytes)
    assert len(n) == 16


def test_random_nonce_returns_different_values():
    a = random_nonce()
    b = random_nonce()
    assert a != b


def test_xor_bytes_symmetric():
    a = b"\xaa" * 16
    b = b"\x55" * 16
    assert xor_bytes(a, b) == b"\xff" * 16
    assert xor_bytes(xor_bytes(a, b), b) == a


def test_xor_bytes_rejects_length_mismatch():
    with pytest.raises(ValueError, match="lengths differ"):
        xor_bytes(b"\x00" * 8, b"\x00" * 16)


def test_derive_session_key_deterministic():
    master = b"\xa1" * 16
    n_c = b"\x10" * 16
    n_p = b"\x20" * 16
    k1 = derive_session_key(master, n_c, n_p)
    k2 = derive_session_key(master, n_c, n_p)
    assert k1 == k2
    assert len(k1) == 16


def test_derive_session_key_depends_on_inputs():
    master = b"\xa1" * 16
    n_c = b"\x10" * 16
    n_p = b"\x20" * 16
    base = derive_session_key(master, n_c, n_p)
    # Change one input at a time — result must differ.
    assert derive_session_key(bytes(16), n_c, n_p) != base
    assert derive_session_key(master, bytes(16), n_p) != base
    assert derive_session_key(master, n_c, bytes(16)) != base


def test_derive_session_key_rejects_short_nonces():
    master = b"\xa1" * 16
    with pytest.raises(ValueError):
        derive_session_key(master, b"\x00", b"\x00" * 16)
