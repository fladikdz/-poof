// Inspect AnyTo's loaded modules to confirm WinBLEPeripheral.dll is up.

console.log('=== Loaded modules containing WinBLE / pgp / ble ===');
const mods = Process.enumerateModules();
let found = null;
for (const m of mods) {
    const lower = m.name.toLowerCase();
    if (lower.indexOf('winble') !== -1 || lower.indexOf('pgp') !== -1) {
        console.log(`  ${m.name}  base=${m.base}  size=0x${m.size.toString(16)}`);
        if (lower.indexOf('winble') !== -1) found = m;
    }
}

if (!found) {
    console.log('!! WinBLEPeripheral.dll NOT loaded. User must switch AnyTo to Bluetooth mode first.');
} else {
    console.log('\n=== WinBLEPeripheral.dll exports ===');
    const exps = found.enumerateExports();
    for (const e of exps) {
        console.log(`  ${e.name}  @ ${e.address}`);
    }
}
