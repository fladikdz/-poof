// Full enumeration of loaded modules + look for bluetooth-related ones

console.log('=== ALL loaded modules (filtered) ===');
const mods = Process.enumerateModules();
console.log(`Total modules: ${mods.length}`);

console.log('\n--- Bluetooth-related ---');
for (const m of mods) {
    const lower = m.name.toLowerCase();
    if (lower.indexOf('blue') !== -1 || lower.indexOf('ble') !== -1 ||
        lower.indexOf('btapi') !== -1 || lower.indexOf('bthprops') !== -1 ||
        lower.indexOf('wpd') !== -1) {
        console.log(`  ${m.name}  base=${m.base}`);
    }
}

console.log('\n--- iMyFone / MF / WinBLE ---');
for (const m of mods) {
    const lower = m.name.toLowerCase();
    if (lower.indexOf('mf') !== -1 || lower.indexOf('imy') !== -1 ||
        lower.indexOf('winble') !== -1 || lower.indexOf('pgp') !== -1) {
        console.log(`  ${m.name}  base=${m.base}`);
    }
}
