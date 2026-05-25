// poof companion — sideloaded iOS app that acts as a Pokémon Go Plus BLE
// peripheral, reports drift between spoofed and real coordinates back to the
// desktop poof.exe, and (later) provides a DNS-Intercept feature for >20 km
// teleports.
//
// Architecture mirrors iMyFone AnyTo's "iGoHotspot" — the BLE peripheral and
// any DNS work happens on the iOS side (iOS lets sideloaded apps do BLE
// peripheral without an MFi cert, unlike Windows WinRT). The desktop poof app
// remains the UI/control plane; this companion is the iOS-side data plane.

import SwiftUI

@main
struct PoofCompanionApp: App {
    @StateObject private var session = PoofSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
        }
    }
}
