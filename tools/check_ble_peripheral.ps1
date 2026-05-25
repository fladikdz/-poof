# Check if any Bluetooth adapter on this PC supports BLE Peripheral role.
# Pure PowerShell 5.1+ (built into Windows 10/11). No Python, no installs.
#
# How to run on a target PC:
#   1. Copy this .ps1 file to the PC (USB stick, email, OneDrive - any way)
#   2. Right-click Start -> "Windows PowerShell" (regular user is fine)
#   3. Allow script execution for this session:
#        Set-ExecutionPolicy -Scope Process Bypass -Force
#   4. Run:
#        .\check_ble_peripheral.ps1
#
# Output: for each BT adapter, shows whether peripheral role is supported.
# If any line says "Peripheral role: True" -> that adapter can do PGP emulation.

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# Helper to await a WinRT IAsyncOperation<T> synchronously from PowerShell.
# Type lives in the System namespace (assembly System.Runtime.WindowsRuntime.dll).
$asTaskGeneric = ([WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and `
                   $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await {
    param($WinRtTask, $ResultType)
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

# Force-load the WinRT types we need.
[void][Windows.Devices.Bluetooth.BluetoothAdapter, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
[void][Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType = WindowsRuntime]
[void][Windows.Devices.Radios.Radio, Windows.Devices.Radios, ContentType = WindowsRuntime]

# Enumerate all Bluetooth adapters via AQS filter.
# FindAllAsync has multiple overloads; pass empty additional-properties list to force
# the (aqsFilter, additionalProperties) overload instead of (deviceClass) which takes an int.
$selector = [Windows.Devices.Bluetooth.BluetoothAdapter]::GetDeviceSelector()
$emptyProps = New-Object 'System.Collections.Generic.List[string]'
$devices = Await ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($selector, $emptyProps)) `
                 ([Windows.Devices.Enumeration.DeviceInformationCollection])

Write-Host ""
Write-Host "Found $($devices.Count) Bluetooth adapter(s)." -ForegroundColor Cyan
Write-Host ""

if ($devices.Count -eq 0) {
    Write-Host "No BT adapters detected. Plug one in and re-run." -ForegroundColor Yellow
    exit 1
}

$anyPeripheral = $false
$i = 0
foreach ($dev in $devices) {
    $i++
    Write-Host "--- Adapter #$i ---" -ForegroundColor White
    Write-Host "  Name:    $($dev.Name)"
    Write-Host "  Id:      $($dev.Id)"
    Write-Host "  Enabled: $($dev.IsEnabled)"

    try {
        $adapter = Await ([Windows.Devices.Bluetooth.BluetoothAdapter]::FromIdAsync($dev.Id)) `
                         ([Windows.Devices.Bluetooth.BluetoothAdapter])
    } catch {
        Write-Host "  (failed to open: $_)" -ForegroundColor Red
        Write-Host ""
        continue
    }
    if (-not $adapter) {
        Write-Host "  (BluetoothAdapter.FromIdAsync returned null)" -ForegroundColor Red
        Write-Host ""
        continue
    }

    $mac = "{0:X12}" -f $adapter.BluetoothAddress
    $macFmt = ($mac -split '(..)' | Where-Object { $_ }) -join ':'

    $peripheral = $adapter.IsPeripheralRoleSupported
    if ($peripheral) { $anyPeripheral = $true }
    $marker = if ($peripheral) { "  <<< YES, USE THIS" } else { "" }

    Write-Host "  MAC:                 $macFmt"
    Write-Host "  Classic BT:          $($adapter.IsClassicSupported)"
    Write-Host "  BLE:                 $($adapter.IsLowEnergySupported)"
    Write-Host "  Central role:        $($adapter.IsCentralRoleSupported)"
    if ($peripheral) {
        Write-Host "  Peripheral role:     True$marker" -ForegroundColor Green
    } else {
        Write-Host "  Peripheral role:     False" -ForegroundColor Yellow
    }
    Write-Host "  Adv. offload:        $($adapter.IsAdvertisementOffloadSupported)"
    Write-Host "  Extended adv.:       $($adapter.IsExtendedAdvertisingSupported)"

    try {
        $radio = Await ($adapter.GetRadioAsync()) ([Windows.Devices.Radios.Radio])
        if ($radio) {
            Write-Host "  Radio:               $($radio.Name)  state=$($radio.State)"
            if ($radio.State -ne [Windows.Devices.Radios.RadioState]::On) {
                Write-Host "  WARNING: radio not ON; toggle BT on or check Device Manager." -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "  Radio query failed: $_" -ForegroundColor Yellow
    }
    Write-Host ""
}

if ($anyPeripheral) {
    Write-Host "OK: at least one adapter supports peripheral role." -ForegroundColor Green
    Write-Host "    PGP-style BLE emulation can run on it."
    exit 0
} else {
    Write-Host "!! None of the present adapters support peripheral role." -ForegroundColor Yellow
    Write-Host "   Candidates that usually work:"
    Write-Host "     - CSR8510-based dongles (~`$5-10) - cheapest reliable option"
    Write-Host "     - BT 5.0 dongles with RTL8761B chip (TP-Link UB500, Asus BT500)"
    Write-Host "   Avoid: any BT 4.0 dongle that does not explicitly mention peripheral mode."
    exit 2
}
