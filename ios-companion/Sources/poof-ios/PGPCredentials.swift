// Where the PGP master key + per-device cert live on iOS.
//
// We never bundle real credentials in the .ipa (publishing leaked keys is
// legally risky). Instead the app reads them from:
//   - the iOS app's Documents directory at "pgp_master_key.bin" (16 raw bytes)
//   - optionally "pgp_session_cert.bin" (16 raw bytes) preserved across launches
//
// User adds those files via the Files app (iOS shares Documents through it),
// AltStore's Documents tab, or copies them from desktop poof via the BLE sync
// service later. If files are missing, the app falls back to 16 zero bytes —
// state machine still runs but Pokémon GO server validation will reject.

import Foundation

struct PGPCredentials {
    let masterKey: Data   // 16 bytes, AES-128
    let cert: Data?       // 16 bytes optional (per-session)

    static func load() -> PGPCredentials {
        let docs = (try? FileManager.default.url(
            for: .documentDirectory, in: .userDomainMask,
            appropriateFor: nil, create: true)) ?? URL(fileURLWithPath: NSTemporaryDirectory())

        let keyURL = docs.appendingPathComponent("pgp_master_key.bin")
        let certURL = docs.appendingPathComponent("pgp_session_cert.bin")

        let key: Data
        if let data = try? Data(contentsOf: keyURL), data.count == 16 {
            key = data
        } else {
            key = Data(repeating: 0, count: 16)
        }
        let cert: Data?
        if let data = try? Data(contentsOf: certURL), data.count == 16 {
            cert = data
        } else {
            cert = nil
        }
        return PGPCredentials(masterKey: key, cert: cert)
    }

    static func persistCert(_ cert: Data) {
        guard cert.count == 16,
              let docs = try? FileManager.default.url(
                for: .documentDirectory, in: .userDomainMask,
                appropriateFor: nil, create: true) else { return }
        let url = docs.appendingPathComponent("pgp_session_cert.bin")
        try? cert.write(to: url, options: .atomic)
    }
}
