import Foundation
import Combine
import CoreLocation

// Top-level state object — owns the location manager and the BLE peripheral.
// SwiftUI views observe this for live updates.
final class PoofSession: ObservableObject {
    @Published var realLocation: CLLocation? = nil
    @Published var locationAuthorization: CLAuthorizationStatus = .notDetermined
    @Published var blePeripheralStatus: BlePeripheralStatus = .stopped
    @Published var bleSubscribersCount: Int = 0
    @Published var lastLogLine: String = ""

    private(set) lazy var locationManager: LocationManager = {
        LocationManager(onUpdate: { [weak self] loc in
            DispatchQueue.main.async { self?.realLocation = loc }
        }, onAuthChange: { [weak self] auth in
            DispatchQueue.main.async { self?.locationAuthorization = auth }
        })
    }()

    private(set) lazy var blePeripheral: BLEPeripheralManager = {
        BLEPeripheralManager(log: { [weak self] line in
            DispatchQueue.main.async {
                self?.lastLogLine = line
                print("[poof] \(line)")
            }
        }, onStatusChange: { [weak self] status in
            DispatchQueue.main.async { self?.blePeripheralStatus = status }
        }, onSubscribersChange: { [weak self] n in
            DispatchQueue.main.async { self?.bleSubscribersCount = n }
        })
    }()

    func start() {
        locationManager.start()
    }

    func stop() {
        locationManager.stop()
        blePeripheral.stop()
    }
}

enum BlePeripheralStatus: String {
    case stopped = "Stopped"
    case starting = "Starting…"
    case advertising = "Advertising as 'Pokemon GO Plus'"
    case error = "Error"
}
