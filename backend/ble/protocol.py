"""PGP handshake state machine.

This layer holds the *control flow* of the Pokémon Go Plus authentication
protocol — what bytes go where, in what order, with which encryption key. It
deliberately knows nothing about Bluetooth, sockets, or async loops. It just
exposes:

  - `PgpSession` — per-connection state
  - `handle_central_write(char_uuid, data) -> list[Outgoing]` — feed in writes
    received on Sfida characteristics, get back zero or more replies to send

Use this from the BLE transport layer (Layer 4, WinRT GATT-server) or from
tests with a mocked central.

NB: The exact byte-level flow below is the *skeleton* derived from pgpemu /
documented PGP reverse engineering. Specific framing constants, payload
lengths, and reply timing should be cross-checked against pgpemu source when
hardware integration starts — there are minor variations between PGP firmware
revisions.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import constants
from .crypto import (
    aes_ctr_apply,
    aes_ecb_decrypt,
    aes_ecb_encrypt,
    derive_session_key,
    random_nonce,
    xor_bytes,
)


class State(enum.Enum):
    IDLE = "idle"
    AWAIT_FIRST_PAIR_NONCE = "await_first_pair_nonce"
    AWAIT_RECONNECT_NONCE = "await_reconnect_nonce"
    AWAIT_CERT_RESPONSE = "await_cert_response"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"


@dataclass
class Outgoing:
    """One thing the emulator needs to send back to the central.

    `notify` means: send a GATT notification on `char_uuid` with `data`.
    The transport layer is responsible for the actual GATT mechanics.
    """
    char_uuid: uuid.UUID
    data: bytes
    kind: str = "notify"  # "notify" or "response"


@dataclass
class PgpSession:
    master_key: bytes
    # Per-device stable cert (16 bytes) — generated on first pair, persisted by
    # the caller across reconnects. Pass None to force a fresh first-pair flow.
    cert: Optional[bytes] = None

    state: State = State.IDLE
    central_nonce: bytes = b""
    pgp_nonce: bytes = b""
    session_key: bytes = b""

    # Last command code seen on Sfida-Commands (from the central side).
    last_command: int = constants.SfidaCommand.NONE

    # Outgoing buffer the transport layer drains.
    _outbox: list[Outgoing] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.master_key) != 16:
            raise ValueError("master_key must be 16 bytes")
        if self.cert is not None and len(self.cert) != 16:
            raise ValueError("cert must be 16 bytes if provided")

    # ------------------------------------------------------------------
    # public surface used by the transport
    # ------------------------------------------------------------------

    def on_central_write(self, char_uuid: uuid.UUID, data: bytes) -> list[Outgoing]:
        """Called by the transport when the central writes on a Sfida char.

        Returns a list of outgoing packets the transport should deliver
        (typically via GATT notifications).
        """
        if char_uuid == constants.SFIDA_COMMANDS_CHAR_UUID:
            self._handle_command(data)
        elif char_uuid == constants.SFIDA_CENTRAL_CHAR_UUID:
            self._handle_central_payload(data)
        elif char_uuid == constants.SFIDA_DATA_CHAR_UUID:
            self._handle_data_payload(data)
        else:
            # Writes on LED / etc. are accepted but ignored by the auth FSM.
            pass

        out = self._outbox
        self._outbox = []
        return out

    # ------------------------------------------------------------------
    # internal handlers
    # ------------------------------------------------------------------

    def _emit(self, char: uuid.UUID, data: bytes) -> None:
        self._outbox.append(Outgoing(char_uuid=char, data=data))

    def _handle_command(self, data: bytes) -> None:
        if not data:
            return
        cmd = data[0]
        self.last_command = cmd
        if cmd == constants.SfidaCommand.REQ_FIRST_PAIR:
            self._begin_first_pair()
        elif cmd == constants.SfidaCommand.REQ_NEW_CONNECTION:
            self._begin_reconnect()
        else:
            # Unknown command — stay idle, log if needed.
            pass

    def _begin_first_pair(self) -> None:
        """Step 1 of first pair: generate our nonce, advertise readiness."""
        self.pgp_nonce = random_nonce(16)
        self.state = State.AWAIT_FIRST_PAIR_NONCE
        # Tell central we're ready and hand it our nonce on the Data characteristic.
        self._emit(
            constants.SFIDA_COMMANDS_CHAR_UUID,
            bytes([constants.SfidaCommand.READY]),
        )
        self._emit(constants.SFIDA_DATA_CHAR_UUID, self.pgp_nonce)

    def _begin_reconnect(self) -> None:
        """Step 1 of reconnect: requires a stored cert from a prior first-pair."""
        if self.cert is None:
            # Can't reconnect — fall back to first-pair flow.
            self._begin_first_pair()
            return
        self.pgp_nonce = random_nonce(16)
        self.state = State.AWAIT_RECONNECT_NONCE
        self._emit(
            constants.SFIDA_COMMANDS_CHAR_UUID,
            bytes([constants.SfidaCommand.READY]),
        )
        self._emit(constants.SFIDA_DATA_CHAR_UUID, self.pgp_nonce)

    def _handle_central_payload(self, data: bytes) -> None:
        """Step 2: central sent its nonce / encrypted blob on Central char."""
        if self.state == State.AWAIT_FIRST_PAIR_NONCE:
            if len(data) != 16:
                self._fail()
                return
            self.central_nonce = data
            # Derive session key from both nonces.
            self.session_key = derive_session_key(
                self.master_key, self.central_nonce, self.pgp_nonce
            )
            # Mint a fresh cert for this device — encrypt random material with
            # the session key. Same material is given to central in cleartext
            # via Data char (so it can derive verification value); central later
            # echoes it back encrypted for verification.
            self.cert = random_nonce(16)
            self._emit(constants.SFIDA_DATA_CHAR_UUID, self.cert)
            self.state = State.AWAIT_CERT_RESPONSE
            return

        if self.state == State.AWAIT_RECONNECT_NONCE:
            if len(data) != 16:
                self._fail()
                return
            self.central_nonce = data
            # Reconnect uses (master_key XOR cert) as the effective key.
            assert self.cert is not None
            effective_key = xor_bytes(self.master_key, self.cert)
            self.session_key = derive_session_key(
                effective_key, self.central_nonce, self.pgp_nonce
            )
            self.state = State.AWAIT_CERT_RESPONSE
            return

        # Unexpected write — ignore.

    def _handle_data_payload(self, data: bytes) -> None:
        """Step 3: central sent the encrypted verification value on Data char."""
        if self.state != State.AWAIT_CERT_RESPONSE:
            return
        # Verify central's response: decrypt their reply, compare against
        # the proof we'd compute ourselves.
        try:
            decrypted = aes_ctr_apply(self.session_key, self.pgp_nonce, data)
        except Exception:
            self._fail()
            return

        expected = self._expected_verification()
        if decrypted == expected:
            self.state = State.AUTHENTICATED
            self._emit(
                constants.SFIDA_COMMANDS_CHAR_UUID,
                bytes([constants.SfidaCommand.AUTH_OK]),
            )
        else:
            self._fail()

    def _expected_verification(self) -> bytes:
        """Reference plaintext the central must produce to prove cert knowledge."""
        # The standard pattern: encrypt the central_nonce with the cert under
        # AES-ECB; that's the value central computes and sends back encrypted
        # under the session key.
        assert self.cert is not None
        return aes_ecb_encrypt(self.cert, self.central_nonce)

    def _fail(self) -> None:
        self.state = State.FAILED
        self._emit(
            constants.SFIDA_COMMANDS_CHAR_UUID,
            bytes([constants.SfidaCommand.AUTH_FAILED]),
        )
