import SwiftUI
import CoreLocation

struct RootView: View {
    @EnvironmentObject var session: PoofSession

    var body: some View {
        NavigationStack {
            List {
                Section("Location") {
                    HStack {
                        Text("Authorization")
                        Spacer()
                        Text(authText(session.locationAuthorization))
                            .foregroundStyle(authColor(session.locationAuthorization))
                    }
                    if let loc = session.realLocation {
                        coordRow(label: "Latitude",  value: String(format: "%.6f", loc.coordinate.latitude))
                        coordRow(label: "Longitude", value: String(format: "%.6f", loc.coordinate.longitude))
                        coordRow(label: "Accuracy",  value: String(format: "±%.1f m", loc.horizontalAccuracy))
                        coordRow(label: "Updated",   value: relative(loc.timestamp))
                    } else {
                        Text("Waiting for first fix…")
                            .foregroundStyle(.secondary)
                    }
                    Button(session.locationManager.isRunning ? "Stop" : "Start") {
                        if session.locationManager.isRunning {
                            session.locationManager.stop()
                        } else {
                            session.locationManager.start()
                        }
                    }
                }

                Section("BLE / Pokémon Go Plus") {
                    HStack {
                        Text("Status")
                        Spacer()
                        Text(session.blePeripheralStatus.rawValue)
                            .foregroundStyle(statusColor(session.blePeripheralStatus))
                    }
                    HStack {
                        Text("Subscribed centrals")
                        Spacer()
                        Text("\(session.bleSubscribersCount)")
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Button("Start advertising") {
                            session.blePeripheral.start()
                        }
                        .disabled(session.blePeripheralStatus != .stopped &&
                                  session.blePeripheralStatus != .error)
                        Spacer()
                        Button("Stop") {
                            session.blePeripheral.stop()
                        }
                        .disabled(session.blePeripheralStatus == .stopped)
                    }
                    Text("Advertises as 'Pokemon GO Plus'. Without real PGP credentials the handshake will run but Pokémon GO server validation will reject.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Log") {
                    Text(session.lastLogLine.isEmpty ? "—" : session.lastLogLine)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("poof companion")
        }
        .onAppear { session.start() }
    }

    private func coordRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value).font(.system(.body, design: .monospaced))
                .foregroundStyle(.secondary)
        }
    }

    private func authText(_ s: CLAuthorizationStatus) -> String {
        switch s {
        case .notDetermined: return "Not asked yet"
        case .restricted: return "Restricted"
        case .denied: return "Denied — enable in Settings"
        case .authorizedAlways: return "Always"
        case .authorizedWhenInUse: return "When in use"
        @unknown default: return "Unknown"
        }
    }

    private func authColor(_ s: CLAuthorizationStatus) -> Color {
        switch s {
        case .authorizedAlways, .authorizedWhenInUse: return .green
        case .notDetermined: return .secondary
        default: return .red
        }
    }

    private func statusColor(_ s: BlePeripheralStatus) -> Color {
        switch s {
        case .advertising: return .green
        case .error: return .red
        case .starting: return .orange
        case .stopped: return .secondary
        }
    }

    private func relative(_ d: Date) -> String {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .short
        return f.localizedString(for: d, relativeTo: Date())
    }
}
