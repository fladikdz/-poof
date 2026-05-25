// PGP handshake state machine — Swift port of the Python state machine in
// `backend/ble/protocol.py`. Same flows: first-pair and reconnect.
//
// Real credentials must be plugged in via PGPCredentials (separate file).
// Without them, the machine still walks through the byte-level dance — useful
// for testing pairing flow on iOS — but Pokémon GO server validation will
// reject because the cert / device key are not real.

import CoreBluetooth
import Foundation

struct OutgoingPacket {
    let charUUID: CBUUID
    let data: Data
}

enum HandshakeState {
    case idle
    case awaitFirstPairNonce
    case awaitReconnectNonce
    case awaitCertResponse
    case authenticated
    case failed
}

final class PGPHandshake {
    private(set) var state: HandshakeState = .idle
    private var pgpNonce: Data = Data()
    private var centralNonce: Data = Data()
    private var sessionKey: Data = Data()
    private var cert: Data?

    /// 16-byte AES-128 master key. Loaded from PGPCredentials at construction.
    /// If credentials are missing, falls back to a 16-zero placeholder so the
    /// state machine still runs (but won't authenticate against Pokémon GO).
    private let masterKey: Data

    init(credentials: PGPCredentials = .load()) {
        self.masterKey = credentials.masterKey
        self.cert = credentials.cert  // may be nil — minted at first-pair otherwise
    }

    func onCentralWrite(charUUID: CBUUID, data: Data) -> [OutgoingPacket] {
        switch charUUID {
        case PGPConstants.sfidaCommandsCharUUID:
            return handleCommand(data: data)
        case PGPConstants.sfidaCentralCharUUID:
            return handleCentralPayload(data: data)
        case PGPConstants.sfidaDataCharUUID:
            return handleDataPayload(data: data)
        default:
            return []
        }
    }

    private func handleCommand(data: Data) -> [OutgoingPacket] {
        guard let first = data.first,
              let cmd = PGPConstants.SfidaCommand(rawValue: first) else {
            return []
        }
        switch cmd {
        case .requestFirstPair:  return beginFirstPair()
        case .requestNewConnection: return beginReconnect()
        default: return []
        }
    }

    private func beginFirstPair() -> [OutgoingPacket] {
        pgpNonce = randomBytes(16)
        state = .awaitFirstPairNonce
        return [
            OutgoingPacket(charUUID: PGPConstants.sfidaCommandsCharUUID,
                           data: Data([PGPConstants.SfidaCommand.ready.rawValue])),
            OutgoingPacket(charUUID: PGPConstants.sfidaDataCharUUID, data: pgpNonce),
        ]
    }

    private func beginReconnect() -> [OutgoingPacket] {
        guard cert != nil else { return beginFirstPair() }
        pgpNonce = randomBytes(16)
        state = .awaitReconnectNonce
        return [
            OutgoingPacket(charUUID: PGPConstants.sfidaCommandsCharUUID,
                           data: Data([PGPConstants.SfidaCommand.ready.rawValue])),
            OutgoingPacket(charUUID: PGPConstants.sfidaDataCharUUID, data: pgpNonce),
        ]
    }

    private func handleCentralPayload(data: Data) -> [OutgoingPacket] {
        if state == .awaitFirstPairNonce {
            guard data.count == 16 else { return fail() }
            centralNonce = data
            sessionKey = deriveSessionKey(master: masterKey, a: centralNonce, b: pgpNonce)
            cert = randomBytes(16)
            state = .awaitCertResponse
            return [OutgoingPacket(charUUID: PGPConstants.sfidaDataCharUUID, data: cert!)]
        }
        if state == .awaitReconnectNonce {
            guard data.count == 16 else { return fail() }
            centralNonce = data
            guard let c = cert else { return fail() }
            let effectiveKey = xor(masterKey, c)
            sessionKey = deriveSessionKey(master: effectiveKey, a: centralNonce, b: pgpNonce)
            state = .awaitCertResponse
            return []
        }
        return []
    }

    private func handleDataPayload(data: Data) -> [OutgoingPacket] {
        guard state == .awaitCertResponse else { return [] }
        let decrypted = aesCtrCC(key: sessionKey, iv: pgpNonce, input: data)
        guard let c = cert else { return fail() }
        let expected = aesEcbCC(key: c, input: centralNonce, encrypt: true)
        if decrypted == expected {
            state = .authenticated
            return [OutgoingPacket(charUUID: PGPConstants.sfidaCommandsCharUUID,
                                    data: Data([PGPConstants.SfidaCommand.authOK.rawValue]))]
        }
        return fail()
    }

    private func fail() -> [OutgoingPacket] {
        state = .failed
        return [OutgoingPacket(charUUID: PGPConstants.sfidaCommandsCharUUID,
                                data: Data([PGPConstants.SfidaCommand.authFailed.rawValue]))]
    }
}

// MARK: - helpers

private func randomBytes(_ count: Int) -> Data {
    var d = Data(count: count)
    _ = d.withUnsafeMutableBytes { buf in
        SecRandomCopyBytes(kSecRandomDefault, count, buf.baseAddress!)
    }
    return d
}

private func xor(_ a: Data, _ b: Data) -> Data {
    precondition(a.count == b.count)
    var out = Data(count: a.count)
    for i in 0..<a.count { out[i] = a[i] ^ b[i] }
    return out
}

private func deriveSessionKey(master: Data, a: Data, b: Data) -> Data {
    let combined = xor(a, b)
    return aesEcbCC(key: master, input: combined, encrypt: true)
}
