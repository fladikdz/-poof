// Thin CommonCrypto wrappers used by PGPHandshake (CryptoKit doesn't expose
// raw AES-ECB / AES-CTR with a fixed counter, which the PGP protocol uses).

import CommonCrypto
import Foundation

func aesEcbCC(key: Data, input: Data, encrypt: Bool) -> Data {
    precondition(key.count == 16, "AES-128 key must be 16 bytes")
    precondition(input.count == kCCBlockSizeAES128, "AES block must be 16 bytes")
    var output = Data(count: input.count)
    var bytesWritten = 0
    let status = output.withUnsafeMutableBytes { outPtr in
        input.withUnsafeBytes { inPtr in
            key.withUnsafeBytes { keyPtr in
                CCCrypt(CCOperation(encrypt ? kCCEncrypt : kCCDecrypt),
                        CCAlgorithm(kCCAlgorithmAES128),
                        CCOptions(kCCOptionECBMode),
                        keyPtr.baseAddress, key.count,
                        nil,
                        inPtr.baseAddress, input.count,
                        outPtr.baseAddress, output.count,
                        &bytesWritten)
            }
        }
    }
    precondition(status == kCCSuccess, "CCCrypt ECB failed: \(status)")
    output.count = bytesWritten
    return output
}

func aesCtrCC(key: Data, iv: Data, input: Data) -> Data {
    precondition(key.count == 16, "AES-128 key must be 16 bytes")
    precondition(iv.count == 16, "CTR IV must be 16 bytes")
    var output = Data(count: input.count + kCCBlockSizeAES128)
    var bytesWritten = 0
    var cryptorRef: CCCryptorRef?
    var status = CCCryptorCreateWithMode(
        CCOperation(kCCEncrypt),
        CCMode(kCCModeCTR),
        CCAlgorithm(kCCAlgorithmAES128),
        CCPadding(ccNoPadding),
        (iv as NSData).bytes,
        (key as NSData).bytes, key.count,
        nil, 0, 0,
        CCModeOptions(kCCModeOptionCTR_BE),
        &cryptorRef)
    precondition(status == kCCSuccess, "CCCryptorCreateWithMode failed: \(status)")
    defer { if let c = cryptorRef { CCCryptorRelease(c) } }

    status = output.withUnsafeMutableBytes { outPtr in
        input.withUnsafeBytes { inPtr in
            CCCryptorUpdate(cryptorRef, inPtr.baseAddress, input.count,
                            outPtr.baseAddress, output.count, &bytesWritten)
        }
    }
    precondition(status == kCCSuccess, "CCCryptorUpdate failed: \(status)")
    output.count = bytesWritten
    return output
}
