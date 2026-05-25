# poof companion (iOS)

Sideloaded iOS app — Pokémon Go Plus BLE peripheral, drift monitor, and
(later) DNS-Intercept feature. The desktop `poof.exe` drives location
spoofing; this companion runs on the iPhone itself and provides what the
desktop can't reach (iOS-side BLE peripheral, real-location reporting, DNS
proxy for >20 km teleports).

## How you build it (no Mac required)

We don't build locally. GitHub Actions does it on a free macOS runner.

1. Push this repo to GitHub (private or public both work — public gives
   unlimited macOS-runner minutes; private burns the 2000-min/month allowance).
2. Go to the **Actions** tab → "Build iOS Companion" → **Run workflow**.
   (It also runs automatically on every push that touches `ios-companion/`.)
3. After ~5–10 minutes the workflow produces an artifact named
   **`poof-ios-unsigned-ipa`**. Download the zip from the workflow run.
4. Inside is `poof-ios.ipa` — the unsigned app binary. Re-signed at install
   time by AltStore (next section).

## How you install it (Windows side)

You need **AltStore** to sideload the .ipa using a free Apple ID. AltStore
re-signs the app for your specific Apple ID and pushes it to your iPhone.

### One-time setup

1. **Install AltServer on Windows** from https://altstore.io
   (~50 MB, no admin required).
2. **Install iTunes + iCloud for Windows** from Apple's website
   (AltServer talks to your iPhone via the AMDS service iTunes installs).
   *Skip this if you already have AMDS — we set it up earlier for `poof.exe`.*
3. Connect iPhone to PC via USB and trust the computer.
4. **Install AltStore on iPhone**: right-click the AltServer tray icon →
   "Install AltStore" → choose your iPhone → enter your Apple ID + app-specific
   password (create one at appleid.apple.com).
5. On the iPhone: **Settings → General → VPN & Device Management** → trust
   the developer profile created for your Apple ID.

### Install the app

1. Open the **AltStore app on your iPhone**.
2. Tap **+** at the top → choose `poof-ios.ipa` from your Files (you may need
   to copy it to the iPhone first via AirDrop / iCloud Drive / USB-Files).
3. Wait ~30 seconds for AltStore to re-sign and push to your phone.
4. The "poof companion" icon appears on the home screen.

### Keep the app installed

Free-Apple-ID sideloaded apps expire **every 7 days**. AltStore on iPhone
auto-renews them in the background as long as AltServer is reachable on the
same Wi-Fi network. Plug the PC + iPhone to Wi-Fi at least once a week and
AltStore handles renewals.

Alternative: pay for an Apple Developer account ($99/yr) — apps signed with a
paid cert last 1 year.

## What the app does right now

- Shows the live iOS-reported location (CLLocationManager) for drift
  diagnostics.
- Advertises BLE GATT services matching real Pokémon Go Plus (battery, cert,
  main). Local name **"Pokemon GO Plus"** + correct service UUIDs.
- Runs the AES-CTR handshake state machine when a central (iPhone's own
  Pokémon GO app, or LightBlue scanner for testing) writes to the Sfida chars.
- Without real PGP credentials placed in the app's Documents folder, the
  handshake fails server-side. Local pairing should still go through.

## What's still missing (planned)

- **DNS Intercept** via NetworkExtension framework — blocks
  `gs-loc.apple.com` so iOS Wi-Fi-ALS lookups fail → larger antifrod
  tolerance window for >20 km teleports.
- **BTSyncService** — talks to desktop `poof.exe` over BLE so the desktop can
  push the current spoof coordinate to the companion app live.
- **Real PGP credentials** — must be supplied by the user (extracted from a
  physical Pokémon Go Plus via `pgpemu/firmware-tools/patch.py`). Drop a
  16-byte `pgp_master_key.bin` into the app's Documents folder via the Files
  app to enable real authentication.

## Bundle ID / signing

- Bundle ID `com.poof.companion` is a placeholder. If you sideload through
  AltStore with a free Apple ID, AltStore rewrites the bundle ID automatically
  to fit your team's prefix — you don't need to edit anything.
- The entitlements file requests `dns-proxy` for the upcoming DNS feature.
  Free Apple IDs may not be allowed to use NetworkExtension entitlements,
  in which case DNS Intercept won't work without a paid developer cert.
  We'll cross that bridge when we get there.
