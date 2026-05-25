import CoreLocation

// Reads iOS-reported location and pushes updates upstream. Works in
// background-location mode so the app can keep providing drift info even when
// the user switches to Pokémon GO (background mode requires the Location
// entitlement set in Info.plist).
final class LocationManager: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private let onUpdate: (CLLocation) -> Void
    private let onAuthChange: (CLAuthorizationStatus) -> Void
    private(set) var isRunning = false

    init(onUpdate: @escaping (CLLocation) -> Void,
         onAuthChange: @escaping (CLAuthorizationStatus) -> Void) {
        self.onUpdate = onUpdate
        self.onAuthChange = onAuthChange
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 5    // metres — gentle reporting
        manager.allowsBackgroundLocationUpdates = true
        manager.pausesLocationUpdatesAutomatically = false
    }

    func start() {
        if isRunning { return }
        let status: CLAuthorizationStatus = manager.authorizationStatus
        onAuthChange(status)
        switch status {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .denied, .restricted:
            return  // user has to enable manually in Settings
        case .authorizedAlways, .authorizedWhenInUse:
            manager.startUpdatingLocation()
            isRunning = true
        @unknown default:
            break
        }
    }

    func stop() {
        manager.stopUpdatingLocation()
        isRunning = false
    }

    // MARK: - CLLocationManagerDelegate

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        onAuthChange(status)
        if status == .authorizedAlways || status == .authorizedWhenInUse {
            if !isRunning {
                manager.startUpdatingLocation()
                isRunning = true
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        if let last = locations.last {
            onUpdate(last)
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Most errors are transient (kCLErrorLocationUnknown). Just log silently.
        // Real error handling can come later.
    }
}
