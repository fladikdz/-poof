"""Windows WinRT BLE peripheral transport for the PGP emulator.

Runs on Windows 10/11 hosts with a peripheral-capable BT chip (Intel AX2xx /
AX1xx, Realtek RTL876x, CSR8510, etc.). Mirrors `transport_bluez.py`'s shape
so the platform dispatcher in `transport.py` can pick either one.

Uses `winsdk.windows.devices.bluetooth.*`:
  - `GenericAttributeProfile.GattServiceProvider` to host each service
  - `GenericAttributeProfile.GattLocalCharacteristic` for each char
  - `Advertisement.BluetoothLEAdvertisementPublisher` to advertise local name
    + service UUID

Threading: WinRT calls return awaitable IAsyncOperation objects which
`winsdk` lets us `await` directly from asyncio. We keep references to all
ServiceProviders/Characteristics on `self` so they don't get GC'd while the
peripheral is up.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import uuid as uuid_mod
from typing import Optional

from . import constants
from .protocol import Outgoing, PgpSession


logger = logging.getLogger(__name__)


class WinrtPeripheralNotSupported(RuntimeError):
    """The BT adapter doesn't support peripheral role on this Windows host."""


def _uuid_to_winrt(u: uuid_mod.UUID):
    """Convert Python uuid.UUID -> winsdk GUID."""
    # winsdk accepts strings in standard {xxxxxxxx-xxxx-...} form.
    return uuid_mod.UUID(str(u))


def _bytes_to_buffer(data: bytes):
    """Convert Python bytes to a WinRT IBuffer via DataWriter."""
    from winsdk.windows.storage.streams import DataWriter
    writer = DataWriter()
    writer.write_bytes(bytes(data))
    return writer.detach_buffer()


def _buffer_to_bytes(buf) -> bytes:
    """Convert WinRT IBuffer back to Python bytes.
    DataReader.read_bytes takes a writable buffer (bytearray) and fills it
    in-place — it does NOT return the bytes."""
    from winsdk.windows.storage.streams import DataReader
    if buf.length == 0:
        return b""
    reader = DataReader.from_buffer(buf)
    out = bytearray(buf.length)
    reader.read_bytes(out)
    return bytes(out)


class PgpWinrtPeripheral:
    """Run an emulated Pokémon Go Plus on the local WinRT Bluetooth radio.

    Lifecycle:
        peri = PgpWinrtPeripheral(master_key=..., cert=...)
        await peri.start()    # creates services, registers, starts advertising
        # ... iPhone discovers, pairs, handshake goes through PgpSession ...
        await peri.stop()
    """

    def __init__(self, master_key: bytes, cert: Optional[bytes] = None) -> None:
        self.session = PgpSession(master_key=master_key, cert=cert)
        self._started = False
        # Strong refs to keep WinRT objects alive while we run.
        self._service_providers: list = []   # GattServiceProvider per service
        self._characteristics: dict = {}     # uuid.UUID -> GattLocalCharacteristic
        self._char_tokens: list = []         # event handler tokens (for cleanup)
        self._advertisement_publisher = None  # BluetoothLEAdvertisementPublisher

    async def start(self) -> None:
        await self._step("peripheral capability check", self._ensure_peripheral_supported())
        await self._step("PGP main service", self._build_pgp_main_service())
        await self._step("cert service", self._build_cert_service())
        # Battery service uses a SIG-reserved UUID (0x180F) which some WinRT
        # builds refuse to host locally. Make it best-effort — losing battery
        # alone doesn't break iPhone pairing with PGP.
        try:
            await self._step("battery service (optional)", self._build_battery_service())
        except Exception as exc:
            logger.warning("Battery service skipped: %s", exc)
        await self._step("advertising", self._start_advertising())
        self._started = True
        logger.info("WinRT peripheral advertising as %r", constants.DEVICE_NAME)

    async def _step(self, label: str, coro) -> None:
        """Run a coroutine and re-raise with step-prefixed message on failure."""
        logger.info("BLE step: %s ...", label)
        try:
            await coro
        except Exception as exc:
            msg = f"step '{label}' failed: {type(exc).__name__}: {exc}"
            logger.exception(msg)
            raise RuntimeError(msg) from exc
        logger.info("BLE step: %s OK", label)

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            if self._advertisement_publisher is not None:
                self._advertisement_publisher.stop()
        except Exception as exc:
            logger.debug("publisher.stop() ignored: %s", exc)

        for provider in self._service_providers:
            try:
                provider.stop_advertising()
            except Exception as exc:
                logger.debug("provider.stop_advertising() ignored: %s", exc)

        self._service_providers.clear()
        self._characteristics.clear()
        self._char_tokens.clear()
        self._advertisement_publisher = None
        self._started = False

    # ------------------------------------------------------------------
    # platform / adapter check
    # ------------------------------------------------------------------

    async def _ensure_peripheral_supported(self) -> None:
        from winsdk.windows.devices.bluetooth import BluetoothAdapter
        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None:
            raise WinrtPeripheralNotSupported("No default Bluetooth adapter present.")
        if not adapter.is_peripheral_role_supported:
            raise WinrtPeripheralNotSupported(
                "Default BT adapter does not support peripheral role. "
                "Plug in a peripheral-capable USB BT dongle (CSR8510, RTL8761B, etc.) "
                "or use an Intel-AX-series internal BT card."
            )

    # ------------------------------------------------------------------
    # services / characteristics
    # ------------------------------------------------------------------

    async def _build_battery_service(self) -> None:
        from winsdk.windows.devices.bluetooth.genericattributeprofile import (
            GattServiceProvider,
            GattServiceProviderAdvertisingParameters,
            GattLocalCharacteristicParameters,
            GattCharacteristicProperties,
            GattProtectionLevel,
        )

        provider_result = await GattServiceProvider.create_async(_uuid_to_winrt(constants.BATTERY_SERVICE_UUID))
        provider = provider_result.service_provider
        if provider is None:
            err = getattr(provider_result, "error", "?")
            err_name = getattr(err, "name", str(err))
            raise RuntimeError(
                f"Battery GattServiceProvider.create_async returned None "
                f"(error={err_name}). Standard SIG UUIDs are sometimes blocked "
                f"by Windows for local hosting."
            )

        params = GattLocalCharacteristicParameters()
        params.characteristic_properties = (
            GattCharacteristicProperties.READ | GattCharacteristicProperties.NOTIFY
        )
        params.read_protection_level = GattProtectionLevel.PLAIN
        params.user_description = "Battery Level"
        params.static_value = _bytes_to_buffer(bytes([constants.DEFAULT_BATTERY_LEVEL]))

        params.write_protection_level = GattProtectionLevel.PLAIN
        char_result = await provider.service.create_characteristic_async(
            _uuid_to_winrt(constants.BATTERY_LEVEL_CHAR_UUID), params
        )
        char = char_result.characteristic
        if char is None:
            err = getattr(char_result, "error", "?")
            raise RuntimeError(f"Battery level characteristic create returned None (error={getattr(err, 'name', err)})")
        self._characteristics[constants.BATTERY_LEVEL_CHAR_UUID] = char

        self._service_providers.append(provider)

    async def _build_cert_service(self) -> None:
        from winsdk.windows.devices.bluetooth.genericattributeprofile import (
            GattServiceProvider,
            GattCharacteristicProperties,
        )

        provider_result = await GattServiceProvider.create_async(_uuid_to_winrt(constants.CERT_SERVICE_UUID))
        provider = provider_result.service_provider
        if provider is None:
            err = getattr(provider_result, "error", "?")
            raise RuntimeError(f"Cert GattServiceProvider returned None (error={getattr(err, 'name', err)})")

        await self._add_writable_char(
            provider,
            constants.SFIDA_CENTRAL_CHAR_UUID,
            "Sfida Central",
            GattCharacteristicProperties.WRITE | GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE,
        )
        await self._add_writable_char(
            provider,
            constants.SFIDA_COMMANDS_CHAR_UUID,
            "Sfida Commands",
            GattCharacteristicProperties.READ | GattCharacteristicProperties.WRITE | GattCharacteristicProperties.NOTIFY,
        )
        await self._add_writable_char(
            provider,
            constants.SFIDA_DATA_CHAR_UUID,
            "Sfida Data",
            GattCharacteristicProperties.READ | GattCharacteristicProperties.WRITE | GattCharacteristicProperties.NOTIFY,
        )

        self._service_providers.append(provider)

    async def _build_pgp_main_service(self) -> None:
        from winsdk.windows.devices.bluetooth.genericattributeprofile import (
            GattServiceProvider,
            GattCharacteristicProperties,
        )

        provider_result = await GattServiceProvider.create_async(_uuid_to_winrt(constants.PGP_SERVICE_UUID))
        provider = provider_result.service_provider
        if provider is None:
            err = getattr(provider_result, "error", "?")
            raise RuntimeError(f"PGP main GattServiceProvider returned None (error={getattr(err, 'name', err)})")

        # Most of these are simple static-value characteristics; only LED is
        # interactive (writable). Real PGP firmware emits BUTTON notifications,
        # we don't fake those for MVP.
        await self._add_writable_char(
            provider, constants.LED_CHAR_UUID, "LED",
            GattCharacteristicProperties.WRITE | GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE,
        )
        await self._add_readable_char(
            provider, constants.BUTTON_CHAR_UUID, "Button",
            initial=b"\x00",
            flags_extra="notify",
        )
        await self._add_readable_char(
            provider, constants.BATTERY_LEVEL_PGP_CHAR, "Battery (internal)",
            initial=bytes([constants.DEFAULT_BATTERY_LEVEL]),
        )
        await self._add_readable_char(
            provider, constants.MANUFACTURER_CHAR_UUID, "Manufacturer",
            initial=constants.MANUFACTURER_NAME.encode("utf-8"),
        )
        await self._add_readable_char(
            provider, constants.FIRMWARE_VERSION_CHAR, "Firmware Version",
            initial=constants.DEFAULT_FIRMWARE_VERSION,
        )
        await self._add_writable_char(
            provider, constants.UPDATE_REQUEST_CHAR, "Update Request",
            None,  # default WRITE
        )

        self._service_providers.append(provider)

    async def _add_writable_char(self, provider, uu: uuid_mod.UUID, description: str, props) -> None:
        from winsdk.windows.devices.bluetooth.genericattributeprofile import (
            GattLocalCharacteristicParameters,
            GattCharacteristicProperties,
            GattProtectionLevel,
        )

        if props is None:
            props = GattCharacteristicProperties.WRITE
        params = GattLocalCharacteristicParameters()
        params.characteristic_properties = props
        params.read_protection_level = GattProtectionLevel.PLAIN
        params.write_protection_level = GattProtectionLevel.PLAIN
        params.user_description = description

        result = await provider.service.create_characteristic_async(_uuid_to_winrt(uu), params)
        char = result.characteristic
        if char is None:
            err = getattr(result, "error", "?")
            raise RuntimeError(f"Char {uu} (writable) create returned None (error={getattr(err, 'name', err)})")

        # Hook write event — dispatch to PgpSession.
        peripheral = self

        def _on_write(sender, args):
            try:
                request = args.get_request_async()
                # Note: WinRT IAsyncOperation; can't await from sync handler.
                # Use a workaround: schedule the coroutine on the running loop.
                loop = asyncio.get_event_loop()
                loop.create_task(peripheral._handle_write_event(uu, args))
            except Exception:
                logger.exception("WinRT write-event scheduling failed")

        token = char.add_write_requested(_on_write)
        self._char_tokens.append(token)

        self._characteristics[uu] = char

    async def _add_readable_char(self, provider, uu: uuid_mod.UUID, description: str,
                                  initial: bytes, flags_extra: str = "") -> None:
        from winsdk.windows.devices.bluetooth.genericattributeprofile import (
            GattLocalCharacteristicParameters,
            GattCharacteristicProperties,
            GattProtectionLevel,
        )

        params = GattLocalCharacteristicParameters()
        props = GattCharacteristicProperties.READ
        if "notify" in flags_extra:
            props |= GattCharacteristicProperties.NOTIFY
        params.characteristic_properties = props
        params.read_protection_level = GattProtectionLevel.PLAIN
        params.user_description = description
        params.static_value = _bytes_to_buffer(initial)

        params.write_protection_level = GattProtectionLevel.PLAIN
        result = await provider.service.create_characteristic_async(_uuid_to_winrt(uu), params)
        char = result.characteristic
        if char is None:
            err = getattr(result, "error", "?")
            raise RuntimeError(f"Char {uu} (readable) create returned None (error={getattr(err, 'name', err)})")
        self._characteristics[uu] = char

    async def _handle_write_event(self, char_uuid: uuid_mod.UUID, args) -> None:
        """Process a GattWriteRequest: read value, feed to PgpSession,
        notify-emit any outgoing packets the session produces."""
        try:
            request = await args.get_request_async()
            value_bytes = _buffer_to_bytes(request.value)
            outs = self.session.on_central_write(char_uuid, value_bytes)
            # Respond OK to the writer if it expected a response.
            if request.option.value == 0:  # GattWriteOption.WriteWithResponse
                request.respond()
            for o in outs:
                target = self._characteristics.get(o.char_uuid)
                if target is None:
                    logger.warning("No characteristic for outgoing %s", o.char_uuid)
                    continue
                # Notify subscribed clients.
                buf = _bytes_to_buffer(o.data)
                await target.notify_value_async(buf)
        except Exception:
            logger.exception("WinRT write handling failed for %s", char_uuid)

    # ------------------------------------------------------------------
    # advertising
    # ------------------------------------------------------------------

    async def _start_advertising(self) -> None:
        from winsdk.windows.devices.bluetooth.genericattributeprofile import (
            GattServiceProviderAdvertisingParameters,
        )
        from winsdk.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisementPublisher,
            BluetoothLEAdvertisement,
            BluetoothLEManufacturerData,
        )

        # Tell each service provider to start advertising.
        params = GattServiceProviderAdvertisingParameters()
        params.is_discoverable = True
        params.is_connectable = True
        for provider in self._service_providers:
            provider.start_advertising(params)

        # Add a BluetoothLEAdvertisementPublisher carrying ONLY manufacturer
        # data. Windows BT policy (Intel driver) rejects publisher.start() if
        # the advertisement includes a local_name — that's reserved for system
        # services. Manufacturer data is allowed.
        #
        # Effect on iPhone: the device shows up in Settings -> Bluetooth ->
        # Other Devices using the PC hostname (or "Unnamed") rather than our
        # DEVICE_NAME constant. User can rename their planshet to
        # "Pokemon GO Plus" via Settings -> System -> About -> Rename PC
        # if they want the visible name to match.
        adv = BluetoothLEAdvertisement()
        md = BluetoothLEManufacturerData()
        md.company_id = 0x0157  # Nintendo Co., Ltd.
        md.data = _bytes_to_buffer(b"\x01\x00")
        adv.manufacturer_data.append(md)
        publisher = BluetoothLEAdvertisementPublisher(adv)
        publisher.start()
        self._advertisement_publisher = publisher
