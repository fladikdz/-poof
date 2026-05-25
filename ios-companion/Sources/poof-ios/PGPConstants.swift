// Pokémon Go Plus protocol constants — mirror of `backend/ble/constants.py` in
// the desktop project. UUIDs verified against AnyTo's WinBLEPeripheral.dll
// static analysis and documented open-source emulators (pgpemu).

import CoreBluetooth

enum PGPConstants {
    // Local name advertised to iOS. Pokémon GO recognises this name + UUID.
    static let deviceName = "Pokemon GO Plus"
    static let manufacturerName = "Nintendo"

    // Battery service (standard SIG short UUID 0x180F).
    static let batteryServiceUUID = CBUUID(string: "180F")
    static let batteryLevelCharUUID = CBUUID(string: "2A19")

    // PGP Certificate / Sfida handshake service.
    static let certServiceUUID         = CBUUID(string: "BBE87709-5B89-4433-AB7F-8B8EEF0D8E34")
    static let sfidaCentralCharUUID    = CBUUID(string: "BBE87709-5B89-4433-AB7F-8B8EEF0D8E35")
    static let sfidaCommandsCharUUID   = CBUUID(string: "BBE87709-5B89-4433-AB7F-8B8EEF0D8E36")
    static let sfidaDataCharUUID       = CBUUID(string: "BBE87709-5B89-4433-AB7F-8B8EEF0D8E37")

    // Main PGP service (LED / button / battery / manufacturer / firmware / update).
    static let pgpServiceUUID          = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5B9939AEA")
    static let ledCharUUID             = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5B9939AEB")
    static let buttonCharUUID          = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5b9939AEC")
    static let pgpBatteryCharUUID      = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5B9939AED")
    static let manufacturerCharUUID    = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5B9939AEE")
    static let firmwareCharUUID        = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5B9939AEF")
    static let updateRequestCharUUID   = CBUUID(string: "21C50462-67CB-63A3-5C4C-82B5B9939AF0")

    // Default values that real PGP firmware reports.
    static let defaultBatteryLevel: UInt8 = 80
    static let defaultFirmwareVersion = Data([0x31, 0x2E, 0x30, 0x2E, 0x34])  // "1.0.4"

    // Sfida command codes used over the handshake characteristic.
    enum SfidaCommand: UInt8 {
        case requestFirstPair      = 0x01
        case requestNewConnection  = 0x02
        case ready                 = 0x03
        case authOK                = 0x04
        case authFailed            = 0xFF
    }
}
