// Hosts the Pokémon Go Plus GATT services on iOS via CoreBluetooth's
// CBPeripheralManager. iOS is much more permissive than Windows WinRT here:
// sideloaded apps can advertise arbitrary UUIDs + a local name without any
// MFi certification.
//
// NOTE: PGP authentication uses AES-CTR with a 16-byte master key (plus a
// per-device BLOB + MAC). This file ships only the structural emulation —
// services advertise, characteristics accept writes — but the handshake
// returns a placeholder response. To actually pass Pokémon GO's server-side
// validation, real PGP credentials must be plugged into PGPHandshake.swift.

import CoreBluetooth
import Foundation

final class BLEPeripheralManager: NSObject, CBPeripheralManagerDelegate {
    private let log: (String) -> Void
    private let onStatusChange: (BlePeripheralStatus) -> Void
    private let onSubscribersChange: (Int) -> Void

    private var manager: CBPeripheralManager?
    private var batteryService: CBMutableService?
    private var certService: CBMutableService?
    private var pgpService: CBMutableService?

    private var subscribersByChar: [CBUUID: Set<UUID>] = [:]

    // Mutable references kept so we can call updateValue on them after writes.
    private var sfidaCommandsChar: CBMutableCharacteristic?
    private var sfidaDataChar: CBMutableCharacteristic?
    private var buttonChar: CBMutableCharacteristic?

    private let handshake = PGPHandshake()

    init(log: @escaping (String) -> Void,
         onStatusChange: @escaping (BlePeripheralStatus) -> Void,
         onSubscribersChange: @escaping (Int) -> Void) {
        self.log = log
        self.onStatusChange = onStatusChange
        self.onSubscribersChange = onSubscribersChange
        super.init()
    }

    func start() {
        guard manager == nil else { return }
        onStatusChange(.starting)
        log("Initialising peripheral manager…")
        manager = CBPeripheralManager(delegate: self, queue: nil, options: [
            CBPeripheralManagerOptionShowPowerAlertKey: true,
        ])
    }

    func stop() {
        guard let mgr = manager else { return }
        if mgr.isAdvertising { mgr.stopAdvertising() }
        mgr.removeAllServices()
        manager = nil
        subscribersByChar.removeAll()
        onStatusChange(.stopped)
        log("Peripheral stopped.")
    }

    // MARK: - CBPeripheralManagerDelegate

    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        switch peripheral.state {
        case .poweredOn:
            log("BT powered on, registering services…")
            registerServices(peripheral)
        case .poweredOff:
            log("BT powered off.")
            onStatusChange(.stopped)
        case .unauthorized:
            log("BT not authorised — open Settings → Privacy → Bluetooth.")
            onStatusChange(.error)
        case .unsupported:
            log("BT peripheral unsupported on this device.")
            onStatusChange(.error)
        case .resetting, .unknown:
            log("BT state: \(peripheral.state.rawValue)")
        @unknown default:
            break
        }
    }

    func peripheralManager(_ peripheral: CBPeripheralManager,
                           didAdd service: CBService,
                           error: Error?) {
        if let error {
            log("Failed to add service \(service.uuid): \(error.localizedDescription)")
            onStatusChange(.error)
        } else {
            log("Service \(service.uuid) added.")
        }
    }

    func peripheralManagerDidStartAdvertising(_ peripheral: CBPeripheralManager,
                                              error: Error?) {
        if let error {
            log("Advertising failed: \(error.localizedDescription)")
            onStatusChange(.error)
        } else {
            log("Advertising started.")
            onStatusChange(.advertising)
        }
    }

    func peripheralManager(_ peripheral: CBPeripheralManager,
                           didReceiveRead request: CBATTRequest) {
        // Serve static reads for the read-only characteristics.
        let value: Data?
        switch request.characteristic.uuid {
        case PGPConstants.batteryLevelCharUUID, PGPConstants.pgpBatteryCharUUID:
            value = Data([PGPConstants.defaultBatteryLevel])
        case PGPConstants.manufacturerCharUUID:
            value = PGPConstants.manufacturerName.data(using: .utf8)
        case PGPConstants.firmwareCharUUID:
            value = PGPConstants.defaultFirmwareVersion
        case PGPConstants.buttonCharUUID:
            value = Data([0x00])
        default:
            value = nil
        }
        if let v = value {
            request.value = v
            peripheral.respond(to: request, withResult: .success)
        } else {
            peripheral.respond(to: request, withResult: .attributeNotFound)
        }
    }

    func peripheralManager(_ peripheral: CBPeripheralManager,
                           didReceiveWrite requests: [CBATTRequest]) {
        for req in requests {
            guard let data = req.value else { continue }
            let outs = handshake.onCentralWrite(charUUID: req.characteristic.uuid, data: data)
            for out in outs {
                notify(charUUID: out.charUUID, data: out.data)
            }
        }
        if let first = requests.first {
            peripheral.respond(to: first, withResult: .success)
        }
    }

    func peripheralManager(_ peripheral: CBPeripheralManager,
                           central: CBCentral,
                           didSubscribeTo characteristic: CBCharacteristic) {
        var set = subscribersByChar[characteristic.uuid] ?? []
        set.insert(central.identifier)
        subscribersByChar[characteristic.uuid] = set
        updateSubscriberCount()
        log("Central \(central.identifier.uuidString.prefix(8))… subscribed to \(characteristic.uuid)")
    }

    func peripheralManager(_ peripheral: CBPeripheralManager,
                           central: CBCentral,
                           didUnsubscribeFrom characteristic: CBCharacteristic) {
        var set = subscribersByChar[characteristic.uuid] ?? []
        set.remove(central.identifier)
        subscribersByChar[characteristic.uuid] = set
        updateSubscriberCount()
    }

    // MARK: - helpers

    private func registerServices(_ peripheral: CBPeripheralManager) {
        // Battery service (standard SIG)
        let batteryLevel = CBMutableCharacteristic(
            type: PGPConstants.batteryLevelCharUUID,
            properties: [.read, .notify],
            value: nil,
            permissions: [.readable])
        let battery = CBMutableService(type: PGPConstants.batteryServiceUUID, primary: true)
        battery.characteristics = [batteryLevel]
        peripheral.add(battery)
        batteryService = battery

        // Cert / Sfida service (handshake)
        let sfidaCentral = CBMutableCharacteristic(
            type: PGPConstants.sfidaCentralCharUUID,
            properties: [.write, .writeWithoutResponse],
            value: nil,
            permissions: [.writeable])
        let sfidaCommands = CBMutableCharacteristic(
            type: PGPConstants.sfidaCommandsCharUUID,
            properties: [.read, .write, .notify],
            value: nil,
            permissions: [.readable, .writeable])
        let sfidaData = CBMutableCharacteristic(
            type: PGPConstants.sfidaDataCharUUID,
            properties: [.read, .write, .notify],
            value: nil,
            permissions: [.readable, .writeable])
        sfidaCommandsChar = sfidaCommands
        sfidaDataChar = sfidaData
        let cert = CBMutableService(type: PGPConstants.certServiceUUID, primary: true)
        cert.characteristics = [sfidaCentral, sfidaCommands, sfidaData]
        peripheral.add(cert)
        certService = cert

        // Main PGP service
        let led = CBMutableCharacteristic(
            type: PGPConstants.ledCharUUID,
            properties: [.write, .writeWithoutResponse],
            value: nil,
            permissions: [.writeable])
        let button = CBMutableCharacteristic(
            type: PGPConstants.buttonCharUUID,
            properties: [.read, .notify],
            value: nil,
            permissions: [.readable])
        let pgpBattery = CBMutableCharacteristic(
            type: PGPConstants.pgpBatteryCharUUID,
            properties: [.read],
            value: Data([PGPConstants.defaultBatteryLevel]),
            permissions: [.readable])
        let manuf = CBMutableCharacteristic(
            type: PGPConstants.manufacturerCharUUID,
            properties: [.read],
            value: PGPConstants.manufacturerName.data(using: .utf8),
            permissions: [.readable])
        let firmware = CBMutableCharacteristic(
            type: PGPConstants.firmwareCharUUID,
            properties: [.read],
            value: PGPConstants.defaultFirmwareVersion,
            permissions: [.readable])
        let updateReq = CBMutableCharacteristic(
            type: PGPConstants.updateRequestCharUUID,
            properties: [.write],
            value: nil,
            permissions: [.writeable])
        buttonChar = button
        let pgp = CBMutableService(type: PGPConstants.pgpServiceUUID, primary: true)
        pgp.characteristics = [led, button, pgpBattery, manuf, firmware, updateReq]
        peripheral.add(pgp)
        pgpService = pgp

        // Begin advertising once services are added.
        let adv: [String: Any] = [
            CBAdvertisementDataLocalNameKey: PGPConstants.deviceName,
            CBAdvertisementDataServiceUUIDsKey: [PGPConstants.pgpServiceUUID],
        ]
        peripheral.startAdvertising(adv)
    }

    private func notify(charUUID: CBUUID, data: Data) {
        guard let mgr = manager else { return }
        let char: CBMutableCharacteristic?
        switch charUUID {
        case PGPConstants.sfidaCommandsCharUUID: char = sfidaCommandsChar
        case PGPConstants.sfidaDataCharUUID:     char = sfidaDataChar
        case PGPConstants.buttonCharUUID:        char = buttonChar
        default: char = nil
        }
        guard let c = char else { return }
        let ok = mgr.updateValue(data, for: c, onSubscribedCentrals: nil)
        if !ok {
            log("notify queue full for \(charUUID); will retry on space available")
        }
    }

    private func updateSubscriberCount() {
        let total = subscribersByChar.values.reduce(0) { $0 + $1.count }
        onSubscribersChange(total)
    }
}
