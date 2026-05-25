"""CLI for the PGP BLE emulator.

Usage (Linux / Steam Deck SteamOS):
    python cli_pgp.py status         # print configured UUIDs and platform info
    python cli_pgp.py start          # advertise as 'Pokemon GO Plus', stays open
                                     # until Ctrl+C. iPhone can pair to it.
    python cli_pgp.py clear-cert     # forget stored per-device cert (forces a
                                     # fresh first-pair next time)

The 16-byte master key must be placed in backend/data/pgp_master_key.bin first.
See backend/ble/constants.py for context.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click

from ble import constants
from ble.protocol import State
from ble.transport import PeripheralNotSupported, create_peripheral, describe_runtime_status
from core.paths import user_data_path


# Persisted per-session cert lives in the writable user-data dir alongside the master key.
CERT_PATH = user_data_path("pgp_session_cert.bin")


def _load_cert() -> bytes | None:
    if not CERT_PATH.exists():
        return None
    data = CERT_PATH.read_bytes()
    return data if len(data) == 16 else None


def _save_cert(cert: bytes) -> None:
    CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CERT_PATH.write_bytes(cert)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s  %(levelname)s  %(name)s  %(message)s")


@click.group()
def cli() -> None:
    """PGP BLE emulator CLI."""


@cli.command("status")
def cmd_status() -> None:
    """Print configured constants and platform readiness."""
    click.echo(describe_runtime_status())
    try:
        constants.load_master_key()
        click.echo("  Master key:                 loaded OK")
    except constants.MasterKeyMissingError as exc:
        click.echo(f"  Master key:                 MISSING ({exc.args[0].splitlines()[0]})")
    cert = _load_cert()
    if cert is not None:
        click.echo(f"  Stored session cert:        present ({CERT_PATH})")
    else:
        click.echo("  Stored session cert:        none (will be minted on first pair)")


@cli.command("clear-cert")
def cmd_clear_cert() -> None:
    """Delete the per-device cert so the next session does a fresh first-pair."""
    if CERT_PATH.exists():
        CERT_PATH.unlink()
        click.echo(f"Removed {CERT_PATH}")
    else:
        click.echo("No stored cert; nothing to clear.")


@cli.command("init-test-key")
@click.option("--force", is_flag=True, help="Overwrite an existing key file without prompt.")
def cmd_init_test_key(force: bool) -> None:
    """Write 16 RANDOM bytes to pgp_master_key.bin for end-to-end BLE testing.

    This is NOT a real PGP master key. Local BLE pairing may work and the iPhone
    will see the emulator as a 'Pokemon GO Plus' accessory, but server-side
    validation in Pokemon GO will reject. Use real PGP credentials (extracted
    via yohanes/pgpemu firmware-tools) for actual gameplay.
    """
    import secrets
    target = constants.MASTER_KEY_PATH
    if target.exists() and not force:
        click.echo(f"{target} already exists. Pass --force to overwrite.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(secrets.token_bytes(16))
    click.echo(f"Wrote 16 random bytes to {target}")
    click.echo("")
    click.echo("WARNING: TEST PLACEHOLDER ONLY.")
    click.echo("  - iPhone may discover and attempt to pair the emulator.")
    click.echo("  - Pokemon GO server validation will REJECT this key.")
    click.echo("  - Use this only to verify your BLE peripheral hardware/software works.")


@cli.command("start")
@click.option("--verbose", is_flag=True, help="Enable DEBUG-level logging.")
def cmd_start(verbose: bool) -> None:
    """Begin advertising as 'Pokemon GO Plus' and wait for an iPhone to pair.

    Hold open until Ctrl+C. Cert minted during first pair is persisted so the
    next start runs the (faster) reconnect flow.
    """
    _setup_logging(verbose)
    try:
        master_key = constants.load_master_key()
    except constants.MasterKeyMissingError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    cert = _load_cert()
    if cert is None:
        click.echo("No stored cert; first session will do a full first-pair handshake.")
    else:
        click.echo("Loaded stored cert; reconnect flow will be used if iPhone is already paired.")

    try:
        peripheral = create_peripheral(master_key=master_key, cert=cert)
    except PeripheralNotSupported as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(3)

    asyncio.run(_run(peripheral))


async def _run(peripheral) -> None:
    stop_event = asyncio.Event()

    def _request_stop(*_args) -> None:
        stop_event.set()

    # Ctrl+C / SIGTERM handlers — on Windows asyncio doesn't fully support
    # add_signal_handler so we fall back to KeyboardInterrupt.
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _request_stop)

    try:
        await peripheral.start()
    except Exception as exc:
        click.echo(f"Failed to start peripheral: {exc}", err=True)
        return

    click.echo("Peripheral up. Pair from iPhone Settings -> Bluetooth -> 'Pokemon GO Plus'.")
    click.echo("Ctrl+C to stop.")

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        click.echo("Stopping peripheral...")
        await peripheral.stop()

        # If authenticated, persist the cert for next run.
        if peripheral.session.state == State.AUTHENTICATED and peripheral.session.cert is not None:
            _save_cert(peripheral.session.cert)
            click.echo(f"Saved session cert to {CERT_PATH} for next reconnect.")


if __name__ == "__main__":
    cli()
