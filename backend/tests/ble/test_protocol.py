"""Protocol state-machine tests.

Drives `PgpSession` end-to-end as if we were the central — verifies the FSM
transitions, that the right characteristics get written, and that the AUTH_OK
flag is reached when the central plays by the rules.
"""

from __future__ import annotations

import uuid

import pytest

from backend.ble import constants
from backend.ble.crypto import (
    aes_ctr_apply,
    aes_ecb_encrypt,
    derive_session_key,
    xor_bytes,
)
from backend.ble.protocol import Outgoing, PgpSession, State


MASTER_KEY = b"\x11" * 16


# ----- helpers ------------------------------------------------------------

def _take_emits(out: list[Outgoing]) -> dict[uuid.UUID, bytes]:
    """Index outgoing by characteristic for easier assertions."""
    return {o.char_uuid: o.data for o in out}


def _simulate_central_first_pair(session: PgpSession) -> bytes:
    """Walk a session through a full first-pair flow as a well-behaved central.

    Returns the cert that the session minted for us (so we can re-use it in a
    later reconnect test).
    """
    # Step 1: central asks PGP to start first-pair.
    out = session.on_central_write(
        constants.SFIDA_COMMANDS_CHAR_UUID,
        bytes([constants.SfidaCommand.REQ_FIRST_PAIR]),
    )
    emits = _take_emits(out)
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.READY])
    pgp_nonce = emits[constants.SFIDA_DATA_CHAR_UUID]
    assert len(pgp_nonce) == 16

    # Step 2: central sends its nonce.
    central_nonce = b"\x42" * 16
    out = session.on_central_write(constants.SFIDA_CENTRAL_CHAR_UUID, central_nonce)
    emits = _take_emits(out)
    cert = emits[constants.SFIDA_DATA_CHAR_UUID]
    assert len(cert) == 16

    # Step 3: central derives session_key, computes proof, encrypts under CTR,
    # writes to Data char.
    session_key = derive_session_key(MASTER_KEY, central_nonce, pgp_nonce)
    expected_proof = aes_ecb_encrypt(cert, central_nonce)
    encrypted_proof = aes_ctr_apply(session_key, pgp_nonce, expected_proof)
    out = session.on_central_write(constants.SFIDA_DATA_CHAR_UUID, encrypted_proof)
    emits = _take_emits(out)
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.AUTH_OK])
    assert session.state == State.AUTHENTICATED
    return cert


# ----- happy paths --------------------------------------------------------

def test_first_pair_full_flow_reaches_authenticated():
    session = PgpSession(master_key=MASTER_KEY)
    cert = _simulate_central_first_pair(session)
    assert session.cert == cert


def test_reconnect_uses_stored_cert():
    # First pair to acquire a cert.
    session1 = PgpSession(master_key=MASTER_KEY)
    cert = _simulate_central_first_pair(session1)

    # New session for "reconnect" with the same cert.
    session2 = PgpSession(master_key=MASTER_KEY, cert=cert)
    out = session2.on_central_write(
        constants.SFIDA_COMMANDS_CHAR_UUID,
        bytes([constants.SfidaCommand.REQ_NEW_CONNECTION]),
    )
    emits = _take_emits(out)
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.READY])
    pgp_nonce = emits[constants.SFIDA_DATA_CHAR_UUID]

    # Central nonce + reconnect math (effective key = master XOR cert).
    central_nonce = b"\x88" * 16
    out = session2.on_central_write(constants.SFIDA_CENTRAL_CHAR_UUID, central_nonce)
    # Reconnect does not re-emit cert — session moves silently to AWAIT_CERT_RESPONSE.
    assert session2.state == State.AWAIT_CERT_RESPONSE

    effective_key = xor_bytes(MASTER_KEY, cert)
    session_key = derive_session_key(effective_key, central_nonce, pgp_nonce)
    proof = aes_ecb_encrypt(cert, central_nonce)
    encrypted_proof = aes_ctr_apply(session_key, pgp_nonce, proof)
    out = session2.on_central_write(constants.SFIDA_DATA_CHAR_UUID, encrypted_proof)
    emits = _take_emits(out)
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.AUTH_OK])
    assert session2.state == State.AUTHENTICATED


def test_reconnect_without_cert_falls_back_to_first_pair():
    session = PgpSession(master_key=MASTER_KEY, cert=None)
    out = session.on_central_write(
        constants.SFIDA_COMMANDS_CHAR_UUID,
        bytes([constants.SfidaCommand.REQ_NEW_CONNECTION]),
    )
    emits = _take_emits(out)
    # Falls back to first-pair behaviour — emits READY + a nonce on DATA.
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.READY])
    assert len(emits[constants.SFIDA_DATA_CHAR_UUID]) == 16
    assert session.state == State.AWAIT_FIRST_PAIR_NONCE


# ----- failure paths ------------------------------------------------------

def test_wrong_proof_fails_handshake():
    session = PgpSession(master_key=MASTER_KEY)
    # Walk into AWAIT_CERT_RESPONSE.
    session.on_central_write(
        constants.SFIDA_COMMANDS_CHAR_UUID,
        bytes([constants.SfidaCommand.REQ_FIRST_PAIR]),
    )
    session.on_central_write(constants.SFIDA_CENTRAL_CHAR_UUID, b"\x42" * 16)
    # Send garbage proof — should fail.
    out = session.on_central_write(constants.SFIDA_DATA_CHAR_UUID, b"\x00" * 16)
    emits = _take_emits(out)
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.AUTH_FAILED])
    assert session.state == State.FAILED


def test_short_central_nonce_fails():
    session = PgpSession(master_key=MASTER_KEY)
    session.on_central_write(
        constants.SFIDA_COMMANDS_CHAR_UUID,
        bytes([constants.SfidaCommand.REQ_FIRST_PAIR]),
    )
    out = session.on_central_write(constants.SFIDA_CENTRAL_CHAR_UUID, b"\x01\x02\x03")
    emits = _take_emits(out)
    assert emits[constants.SFIDA_COMMANDS_CHAR_UUID] == bytes([constants.SfidaCommand.AUTH_FAILED])
    assert session.state == State.FAILED


def test_unknown_command_is_ignored():
    session = PgpSession(master_key=MASTER_KEY)
    out = session.on_central_write(constants.SFIDA_COMMANDS_CHAR_UUID, b"\x99")
    assert out == []
    assert session.state == State.IDLE


def test_writes_on_unrelated_chars_are_silently_accepted():
    session = PgpSession(master_key=MASTER_KEY)
    # Writes on LED char should not break the FSM.
    out = session.on_central_write(constants.LED_CHAR_UUID, b"\xff\x00\x00")
    assert out == []
    assert session.state == State.IDLE


# ----- input validation ---------------------------------------------------

def test_short_master_key_rejected():
    with pytest.raises(ValueError, match="master_key"):
        PgpSession(master_key=b"shortkey")


def test_wrong_size_cert_rejected():
    with pytest.raises(ValueError, match="cert"):
        PgpSession(master_key=MASTER_KEY, cert=b"\x00" * 8)
