"""Sanity check: imports we need for BLE peripheral test."""
import winsdk
from winsdk.windows.devices.bluetooth.genericattributeprofile import (
    GattServiceProvider,
    GattLocalCharacteristicParameters,
    GattCharacteristicProperties,
    GattProtectionLevel,
    GattServiceProviderAdvertisingParameters,
)
from winsdk.windows.devices.bluetooth.advertisement import (
    BluetoothLEAdvertisementPublisher,
    BluetoothLEAdvertisement,
)
from winsdk.windows.devices.bluetooth import BluetoothAdapter
from winsdk.windows.storage.streams import DataWriter, DataReader
from cryptography.hazmat.primitives.ciphers import Cipher
print("All imports OK on planshet")
