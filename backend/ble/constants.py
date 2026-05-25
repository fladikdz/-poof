"""Pokémon Go Plus protocol constants.

UUIDs verified against (a) documented PGP reverse-engineering in open-source
emulators pgpemu / pgemu, and (b) static analysis of iMyFone AnyTo's
WinBLEPeripheral.dll — same exact UUID family in both sources.

The 16-byte AES master key shared across all genuine PGP units is NOT in this
file. It must be placed in `backend/data/pgp_master_key.bin` (binary, exactly
16 bytes). See `load_master_key()`.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from core.paths import user_data_path

# ----- Identity ------------------------------------------------------------

# Advertised local name. iOS pairs by this exact name when listed as accessory.
DEVICE_NAME = "Pokemon GO Plus"
MANUFACTURER_NAME = "Nintendo"

# Suggested MAC OUI to spoof (Nintendo). Last 3 bytes can be random per session.
# Real PGPs use one of these prefixes among others; many tweak this for variety.
NINTENDO_OUI_PREFIXES: tuple[bytes, ...] = (
    bytes.fromhex("B49A95"),
    bytes.fromhex("CC9E00"),
    bytes.fromhex("9CE6E7"),
)

# ----- GATT UUIDs ---------------------------------------------------------
# Battery service is the standard SIG one.
BATTERY_SERVICE_UUID = uuid.UUID("0000180F-0000-1000-8000-00805F9B34FB")
BATTERY_LEVEL_CHAR_UUID = uuid.UUID("00002A19-0000-1000-8000-00805F9B34FB")

# Custom Service 1 — Certificate / Sfida handshake service.
# Base UUID: bbe87709-5b89-4433-ab7f-8b8eef0d8e34
# (AnyTo's WinBLEPeripheral.dll has chars ...e37..e3a; pgpemu uses ...e35..e37)
CERT_SERVICE_UUID         = uuid.UUID("bbe87709-5b89-4433-ab7f-8b8eef0d8e34")
SFIDA_CENTRAL_CHAR_UUID   = uuid.UUID("bbe87709-5b89-4433-ab7f-8b8eef0d8e35")  # write: nonces from central
SFIDA_COMMANDS_CHAR_UUID  = uuid.UUID("bbe87709-5b89-4433-ab7f-8b8eef0d8e36")  # notify: handshake commands
SFIDA_DATA_CHAR_UUID      = uuid.UUID("bbe87709-5b89-4433-ab7f-8b8eef0d8e37")  # read/notify: payload (cert)

# Custom Service 2 — main Pokémon Go Plus service (LED / button / battery / manufacturer).
# Base UUID: 21c50462-67cb-63a3-5c4c-82b5b9939aea
PGP_SERVICE_UUID          = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939aea")
LED_CHAR_UUID             = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939aeb")  # write: LED color/pattern
BUTTON_CHAR_UUID          = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939aec")  # notify: button press events
BATTERY_LEVEL_PGP_CHAR    = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939aed")  # read: internal battery
MANUFACTURER_CHAR_UUID    = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939aee")  # read: "Nintendo"
FIRMWARE_VERSION_CHAR     = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939aef")  # read: e.g. "1.0.4"
UPDATE_REQUEST_CHAR       = uuid.UUID("21c50462-67cb-63a3-5c4c-82b5b9939af0")  # write: firmware update trigger

# ----- Handshake protocol commands ----------------------------------------
# Values observed in pgpemu source / documented reverse engineering.
# Sent from central or PGP via Sfida Commands characteristic.

class SfidaCommand:
    NONE = 0x00
    REQ_FIRST_PAIR = 0x01      # central -> PGP: start first-time pairing
    REQ_NEW_CONNECTION = 0x02  # central -> PGP: start reconnect (existing cert)
    READY = 0x03               # PGP -> central: ready for next step
    AUTH_OK = 0x04             # PGP -> central: handshake successful
    AUTH_FAILED = 0xFF         # PGP -> central: handshake failed


# ----- Default battery / firmware payloads --------------------------------
DEFAULT_BATTERY_LEVEL = 80         # percentage, will get queried during connection
DEFAULT_FIRMWARE_VERSION = b"1.0.4"


# ----- Master key loader --------------------------------------------------
# Lives in the user's per-account data directory (not next to the .exe) so the
# PyInstaller-frozen build can read+write it without elevation on Windows and
# without /opt-style permissions on Linux.
MASTER_KEY_PATH = user_data_path("pgp_master_key.bin")


class MasterKeyMissingError(RuntimeError):
    """Master key file not present or wrong size."""


def load_master_key() -> bytes:
    """Read the 16-byte PGP master AES-128 key from disk.

    The key file is intentionally NOT in the repo — fetch it from any open-source
    PGP emulator (pgpemu / pgemu / WinPokemonGOPlus_developer derivatives) and
    save the 16 raw bytes to `backend/data/pgp_master_key.bin`.

    Raises MasterKeyMissingError with guidance if the file is missing/invalid.
    """
    if not MASTER_KEY_PATH.exists():
        raise MasterKeyMissingError(
            f"Master key file not found at {MASTER_KEY_PATH}.\n"
            "Place a 16-byte binary file containing the PGP AES-128 master key there.\n"
            "Reference: https://github.com/Jesus805/pgpemu (see source for the constant)."
        )
    data = MASTER_KEY_PATH.read_bytes()
    if len(data) != 16:
        raise MasterKeyMissingError(
            f"Master key at {MASTER_KEY_PATH} is {len(data)} bytes, expected exactly 16."
        )
    return data
