"""BlueZ GATT-server peripheral transport for the PGP emulator.

This runs on Linux (target: Steam Deck SteamOS) and uses the BlueZ D-Bus API.
On any other platform `start()` raises immediately — see `transport.py` for the
platform dispatcher.

BlueZ exposes BLE peripheral capabilities through `org.bluez` on the system bus:

  - `org.bluez.GattManager1`        — RegisterApplication(): hand it our object
                                     tree of GattService1 + GattCharacteristic1
                                     and BlueZ wires the radio for us.
  - `org.bluez.LEAdvertisingManager1` — RegisterAdvertisement(): advertise our
                                       local name + service UUIDs.

The pattern is well-documented in BlueZ's own `test/example-gatt-server.py`. We
follow the same pattern, just feeding write events into `PgpSession`.

Run from a SteamOS Konsole (Desktop Mode):

    cd /home/deck/poof  # wherever you put the code
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r backend/requirements.txt
    # Place the 16-byte master key:
    cp <wherever>/pgp_master_key.bin backend/data/pgp_master_key.bin
    python backend/cli_pgp.py start
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from . import constants
from .protocol import Outgoing, PgpSession


logger = logging.getLogger(__name__)


# BlueZ object paths
BLUEZ_SERVICE = "org.bluez"
BLUEZ_ADAPTER_INTERFACE = "org.bluez.Adapter1"
BLUEZ_GATT_MANAGER_INTERFACE = "org.bluez.GattManager1"
BLUEZ_LE_ADV_MANAGER_INTERFACE = "org.bluez.LEAdvertisingManager1"

GATT_SERVICE_INTERFACE = "org.bluez.GattService1"
GATT_CHARACTERISTIC_INTERFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_INTERFACE = "org.bluez.LEAdvertisement1"

APP_PATH = "/com/poof/pgp"
ADV_PATH = "/com/poof/pgp/advertisement"


class BluezNotAvailable(RuntimeError):
    """Raised when not running on Linux or BlueZ daemon is missing."""


def _require_linux() -> None:
    if sys.platform != "linux":
        raise BluezNotAvailable(
            "BlueZ transport only runs on Linux. On Windows you need a "
            "peripheral-capable BT adapter + the WinRT transport (Layer 4 stub)."
        )


# ---------------------------------------------------------------------------
# Helpers — convert bytes to/from D-Bus 'ay' (array of bytes)
# ---------------------------------------------------------------------------

def _to_dbus_bytes(data: bytes):
    """Convert Python bytes to the dbus-next ay (List[int])."""
    return [int(b) for b in data]


def _from_dbus_bytes(value) -> bytes:
    """Convert a dbus-next ay back to Python bytes."""
    return bytes(int(b) for b in value)


# ---------------------------------------------------------------------------
# GATT server skeleton — built around a single PgpSession
# ---------------------------------------------------------------------------

class PgpBluezPeripheral:
    """Top-level BlueZ peripheral for the PGP emulator.

    Lifecycle:
        peri = PgpBluezPeripheral(master_key=..., cert=...)
        await peri.start()
        # iPhone connects, handshake happens, emulator stays advertised
        await peri.stop()
    """

    def __init__(self, master_key: bytes, cert: Optional[bytes] = None,
                 adapter_path: str = "/org/bluez/hci0") -> None:
        self.session = PgpSession(master_key=master_key, cert=cert)
        self.adapter_path = adapter_path
        self._bus = None  # type: ignore[assignment]
        self._service_objects: list = []
        self._char_objects: list = []  # all GattCharacteristicImpl instances
        self._char_by_uuid: dict = {}
        self._adv_object = None
        self._app_object = None
        self._started = False

    async def start(self) -> None:
        _require_linux()
        await self._connect_bus()
        await self._verify_peripheral_role()
        await self._build_app_tree()
        await self._register_application()
        await self._register_advertisement()
        self._started = True
        logger.info("PGP peripheral advertising as %r", constants.DEVICE_NAME)

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self._unregister_advertisement()
            await self._unregister_application()
        finally:
            if self._bus is not None:
                self._bus.disconnect()
            self._started = False

    # ------------------------------------------------------------------
    # bus / adapter
    # ------------------------------------------------------------------

    async def _connect_bus(self) -> None:
        from dbus_next.aio import MessageBus
        from dbus_next import BusType
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    async def _verify_peripheral_role(self) -> None:
        """Sanity-check that BlueZ exposes GattManager1 + LEAdvertisingManager1
        on the chosen adapter — otherwise it cannot host a peripheral."""
        introspection = await self._bus.introspect(BLUEZ_SERVICE, self.adapter_path)
        names = {iface.name for iface in introspection.interfaces}
        missing = []
        if BLUEZ_GATT_MANAGER_INTERFACE not in names:
            missing.append(BLUEZ_GATT_MANAGER_INTERFACE)
        if BLUEZ_LE_ADV_MANAGER_INTERFACE not in names:
            missing.append(BLUEZ_LE_ADV_MANAGER_INTERFACE)
        if missing:
            raise BluezNotAvailable(
                f"Adapter {self.adapter_path} is missing required interfaces: "
                f"{missing}. The host's Bluetooth chip likely doesn't support "
                "peripheral role, or BlueZ is too old (<5.50)."
            )

    # ------------------------------------------------------------------
    # GATT object tree
    # ------------------------------------------------------------------

    async def _build_app_tree(self) -> None:
        # Build service + characteristic objects, expose them on the bus under APP_PATH.
        from dbus_next.service import ServiceInterface, method, dbus_property
        from dbus_next.constants import PropertyAccess

        peripheral = self

        # ---- ObjectManager root (required by BlueZ to enumerate the tree) ----
        class App(ServiceInterface):
            def __init__(self):
                super().__init__("org.freedesktop.DBus.ObjectManager")

            @method()
            def GetManagedObjects(self) -> "a{oa{sa{sv}}}":  # noqa: F722
                return peripheral._managed_objects()

        self._app_object = App()
        self._bus.export(APP_PATH, self._app_object)

        # ---- Each GATT service is one ServiceInterface implementing GattService1 ----
        services = [
            (constants.BATTERY_SERVICE_UUID, [
                (constants.BATTERY_LEVEL_CHAR_UUID, ["read", "notify"], b"\x50"),
            ]),
            (constants.CERT_SERVICE_UUID, [
                (constants.SFIDA_CENTRAL_CHAR_UUID, ["write", "write-without-response"], b""),
                (constants.SFIDA_COMMANDS_CHAR_UUID, ["read", "write", "notify"], b""),
                (constants.SFIDA_DATA_CHAR_UUID, ["read", "write", "notify"], b""),
            ]),
            (constants.PGP_SERVICE_UUID, [
                (constants.LED_CHAR_UUID, ["write"], b""),
                (constants.BUTTON_CHAR_UUID, ["read", "notify"], b"\x00"),
                (constants.BATTERY_LEVEL_PGP_CHAR, ["read"], b"\x50"),
                (constants.MANUFACTURER_CHAR_UUID, ["read"], constants.MANUFACTURER_NAME.encode()),
                (constants.FIRMWARE_VERSION_CHAR, ["read"], constants.DEFAULT_FIRMWARE_VERSION),
                (constants.UPDATE_REQUEST_CHAR, ["write"], b""),
            ]),
        ]

        for svc_idx, (svc_uuid, chars) in enumerate(services):
            svc_path = f"{APP_PATH}/service{svc_idx}"
            svc_obj = _make_service_interface(svc_path, str(svc_uuid), primary=True)
            self._bus.export(svc_path, svc_obj)
            self._service_objects.append((svc_path, svc_obj))

            for char_idx, (char_uuid, flags, initial_value) in enumerate(chars):
                char_path = f"{svc_path}/char{char_idx}"
                char_obj = _make_char_interface(
                    peripheral, char_path, svc_path, str(char_uuid), flags, initial_value,
                )
                self._bus.export(char_path, char_obj)
                self._char_objects.append((char_path, char_obj))
                self._char_by_uuid[char_uuid] = char_obj

    def _managed_objects(self) -> dict:
        """Return the object tree in the format BlueZ expects from
        org.freedesktop.DBus.ObjectManager.GetManagedObjects."""
        result: dict = {}
        # services
        for path, obj in self._service_objects:
            result[path] = {
                GATT_SERVICE_INTERFACE: obj.export_props(),
            }
        # characteristics
        for path, obj in self._char_objects:
            result[path] = {
                GATT_CHARACTERISTIC_INTERFACE: obj.export_props(),
            }
        return result

    # ------------------------------------------------------------------
    # GATT/Adv registration
    # ------------------------------------------------------------------

    async def _register_application(self) -> None:
        intro = await self._bus.introspect(BLUEZ_SERVICE, self.adapter_path)
        proxy = self._bus.get_proxy_object(BLUEZ_SERVICE, self.adapter_path, intro)
        mgr = proxy.get_interface(BLUEZ_GATT_MANAGER_INTERFACE)
        await mgr.call_register_application(APP_PATH, {})

    async def _unregister_application(self) -> None:
        try:
            intro = await self._bus.introspect(BLUEZ_SERVICE, self.adapter_path)
            proxy = self._bus.get_proxy_object(BLUEZ_SERVICE, self.adapter_path, intro)
            mgr = proxy.get_interface(BLUEZ_GATT_MANAGER_INTERFACE)
            await mgr.call_unregister_application(APP_PATH)
        except Exception as exc:
            logger.debug("UnregisterApplication ignored error: %s", exc)

    async def _register_advertisement(self) -> None:
        self._adv_object = _make_advertisement_interface(
            local_name=constants.DEVICE_NAME,
            service_uuids=[str(constants.PGP_SERVICE_UUID)],
        )
        self._bus.export(ADV_PATH, self._adv_object)

        intro = await self._bus.introspect(BLUEZ_SERVICE, self.adapter_path)
        proxy = self._bus.get_proxy_object(BLUEZ_SERVICE, self.adapter_path, intro)
        adv_mgr = proxy.get_interface(BLUEZ_LE_ADV_MANAGER_INTERFACE)
        await adv_mgr.call_register_advertisement(ADV_PATH, {})

    async def _unregister_advertisement(self) -> None:
        try:
            intro = await self._bus.introspect(BLUEZ_SERVICE, self.adapter_path)
            proxy = self._bus.get_proxy_object(BLUEZ_SERVICE, self.adapter_path, intro)
            adv_mgr = proxy.get_interface(BLUEZ_LE_ADV_MANAGER_INTERFACE)
            await adv_mgr.call_unregister_advertisement(ADV_PATH)
        except Exception as exc:
            logger.debug("UnregisterAdvertisement ignored error: %s", exc)

    # ------------------------------------------------------------------
    # Plumbing: characteristic write -> session, session output -> notify
    # ------------------------------------------------------------------

    def dispatch_write(self, char_uuid_str: str, value: bytes) -> None:
        """Called by GattCharacteristicImpl whenever the central writes a value."""
        import uuid as _uuid
        try:
            uu = _uuid.UUID(char_uuid_str)
        except ValueError:
            return
        outs = self.session.on_central_write(uu, value)
        for o in outs:
            target = self._char_by_uuid.get(o.char_uuid)
            if target is None:
                logger.warning("No characteristic registered for outgoing %s", o.char_uuid)
                continue
            target.set_value_and_notify(o.data)


# ---------------------------------------------------------------------------
# Per-object D-Bus interface factories.
#
# dbus-next requires class-level @method / @dbus_property decorators, so we
# build small ServiceInterface subclasses inside factory functions to keep the
# top-level structure flat.
# ---------------------------------------------------------------------------

def _make_service_interface(path: str, uuid_str: str, primary: bool):
    from dbus_next.service import ServiceInterface, dbus_property
    from dbus_next.constants import PropertyAccess

    class GattServiceImpl(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(GATT_SERVICE_INTERFACE)
            self._uuid = uuid_str
            self._primary = primary

        @dbus_property(access=PropertyAccess.READ)
        def UUID(self) -> "s":
            return self._uuid

        @dbus_property(access=PropertyAccess.READ)
        def Primary(self) -> "b":
            return self._primary

        def export_props(self) -> dict:
            return {"UUID": self._uuid, "Primary": self._primary}

    return GattServiceImpl()


def _make_char_interface(peripheral: PgpBluezPeripheral, path: str, service_path: str,
                         uuid_str: str, flags: list[str], initial_value: bytes):
    from dbus_next import Variant
    from dbus_next.service import ServiceInterface, method, dbus_property
    from dbus_next.constants import PropertyAccess

    class GattCharacteristicImpl(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(GATT_CHARACTERISTIC_INTERFACE)
            self._uuid = uuid_str
            self._service = service_path
            self._flags = list(flags)
            self._value = bytes(initial_value)
            self._notifying = False

        @dbus_property(access=PropertyAccess.READ)
        def UUID(self) -> "s":
            return self._uuid

        @dbus_property(access=PropertyAccess.READ)
        def Service(self) -> "o":
            return self._service

        @dbus_property(access=PropertyAccess.READ)
        def Flags(self) -> "as":  # noqa: F722
            return self._flags

        @dbus_property(access=PropertyAccess.READ)
        def Notifying(self) -> "b":
            return self._notifying

        @method()
        def ReadValue(self, options: "a{sv}") -> "ay":  # noqa: F722
            return _to_dbus_bytes(self._value)

        @method()
        def WriteValue(self, value: "ay", options: "a{sv}") -> None:  # noqa: F722
            data = _from_dbus_bytes(value)
            self._value = data
            peripheral.dispatch_write(self._uuid, data)

        @method()
        def StartNotify(self) -> None:
            self._notifying = True

        @method()
        def StopNotify(self) -> None:
            self._notifying = False

        # Public helper used by the peripheral dispatcher.
        def set_value_and_notify(self, data: bytes) -> None:
            self._value = bytes(data)
            if self._notifying:
                # Emit PropertiesChanged so the central receives the notification.
                self.emit_properties_changed({"Value": _to_dbus_bytes(self._value)})

        def export_props(self) -> dict:
            return {
                "UUID": self._uuid,
                "Service": self._service,
                "Flags": self._flags,
                "Notifying": self._notifying,
            }

    return GattCharacteristicImpl()


def _make_advertisement_interface(local_name: str, service_uuids: list[str]):
    from dbus_next.service import ServiceInterface, method, dbus_property
    from dbus_next.constants import PropertyAccess

    class AdvertisementImpl(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(LE_ADVERTISEMENT_INTERFACE)
            self._type = "peripheral"
            self._local_name = local_name
            self._service_uuids = list(service_uuids)

        @dbus_property(access=PropertyAccess.READ)
        def Type(self) -> "s":
            return self._type

        @dbus_property(access=PropertyAccess.READ)
        def LocalName(self) -> "s":
            return self._local_name

        @dbus_property(access=PropertyAccess.READ)
        def ServiceUUIDs(self) -> "as":  # noqa: F722
            return self._service_uuids

        @method()
        def Release(self) -> None:
            pass

    return AdvertisementImpl()
