# Minimal PowerShell+WinRT diagnostic

Add-Type -AssemblyName System.Runtime.WindowsRuntime
Write-Host "Loaded System.Runtime.WindowsRuntime"

$ext = [WindowsRuntimeSystemExtensions]
Write-Host "WindowsRuntimeSystemExtensions type: $ext"

$methods = $ext.GetMethods() | Where-Object { $_.Name -eq 'AsTask' }
Write-Host "AsTask methods found: $($methods.Count)"
foreach ($m in $methods) {
    $params = $m.GetParameters() | ForEach-Object { $_.ParameterType.Name }
    Write-Host "  AsTask($([string]::Join(', ', $params)))"
}

# Pick the simplest single-arg generic overload
$asTaskGeneric = $methods | Where-Object {
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1

Write-Host "Picked: $asTaskGeneric"

function Await {
    param($WinRtTask, $ResultType)
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    Write-Host "  netTask type: $($netTask.GetType().FullName)"
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

[void][Windows.Devices.Bluetooth.BluetoothAdapter, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]

Write-Host ""
Write-Host "Calling BluetoothAdapter.GetDefaultAsync() ..."
$op = [Windows.Devices.Bluetooth.BluetoothAdapter]::GetDefaultAsync()
Write-Host "  op type: $($op.GetType().FullName)"

$adapter = Await $op ([Windows.Devices.Bluetooth.BluetoothAdapter])
Write-Host ""
if ($adapter) {
    Write-Host "Adapter obtained: $($adapter.GetType().FullName)"
    Write-Host "  MAC: $([string]::Format('{0:X12}', $adapter.BluetoothAddress))"
    Write-Host "  Peripheral role: $($adapter.IsPeripheralRoleSupported)"
} else {
    Write-Host "Adapter is null"
}
