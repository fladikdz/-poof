"""Sanity checks on the PGP constants.

Most of this just guards against accidental edits to UUID values that drive
the whole rest of the BLE layer.
"""

from __future__ import annotations

import uuid

import pytest

from backend.ble import constants


def test_battery_service_is_standard_sig_uuid():
    # 0x180F is the BLE-SIG-assigned battery service short UUID.
    assert constants.BATTERY_SERVICE_UUID == uuid.UUID("0000180F-0000-1000-8000-00805F9B34FB")


def test_cert_service_uuids_share_base():
    base = "bbe87709-5b89-4433-ab7f-8b8eef0d8e34"
    base_prefix = base[:-1]  # all but the last hex digit
    assert str(constants.CERT_SERVICE_UUID) == base
    for u in (
        constants.SFIDA_CENTRAL_CHAR_UUID,
        constants.SFIDA_COMMANDS_CHAR_UUID,
        constants.SFIDA_DATA_CHAR_UUID,
    ):
        assert str(u).startswith(base_prefix)


def test_pgp_service_uuids_share_base():
    # The PGP family runs ...9aea .. ...9af0, so the shared prefix is the
    # first 35 chars (the dashed UUID minus the last hex digit).
    base = "21c50462-67cb-63a3-5c4c-82b5b9939aea"
    base_prefix = base[:-2]  # "...9a" — matches both 'ae{b..f}' and 'af0'
    assert str(constants.PGP_SERVICE_UUID) == base
    for u in (
        constants.LED_CHAR_UUID,
        constants.BUTTON_CHAR_UUID,
        constants.BATTERY_LEVEL_PGP_CHAR,
        constants.MANUFACTURER_CHAR_UUID,
        constants.FIRMWARE_VERSION_CHAR,
        constants.UPDATE_REQUEST_CHAR,
    ):
        assert str(u).startswith(base_prefix)


def test_device_name_matches_real_pgp():
    assert constants.DEVICE_NAME == "Pokemon GO Plus"
    assert constants.MANUFACTURER_NAME == "Nintendo"


def test_nintendo_oui_prefixes_are_3_bytes_each():
    assert constants.NINTENDO_OUI_PREFIXES
    for prefix in constants.NINTENDO_OUI_PREFIXES:
        assert isinstance(prefix, bytes)
        assert len(prefix) == 3


def test_load_master_key_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "MASTER_KEY_PATH", tmp_path / "missing.bin")
    with pytest.raises(constants.MasterKeyMissingError, match="not found"):
        constants.load_master_key()


def test_load_master_key_raises_when_wrong_size(tmp_path, monkeypatch):
    p = tmp_path / "key.bin"
    p.write_bytes(b"\x00" * 8)
    monkeypatch.setattr(constants, "MASTER_KEY_PATH", p)
    with pytest.raises(constants.MasterKeyMissingError, match="expected exactly 16"):
        constants.load_master_key()


def test_load_master_key_succeeds_with_16_byte_file(tmp_path, monkeypatch):
    p = tmp_path / "key.bin"
    key = b"\xa1" * 16
    p.write_bytes(key)
    monkeypatch.setattr(constants, "MASTER_KEY_PATH", p)
    assert constants.load_master_key() == key
