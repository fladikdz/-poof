"""Check ALL AnyTo-related processes for WinBLEPeripheral.dll."""

from __future__ import annotations

import sys
import frida


PROCESSES = ["AnyTo.exe", "cef_process.exe", "redBullQuic.exe"]


def check_process(name: str) -> None:
    print(f"\n=== {name} ===")
    try:
        session = frida.attach(name)
    except Exception as e:
        print(f"  attach failed: {e}")
        return
    code = """
    const mods = Process.enumerateModules();
    const interesting = [];
    for (const m of mods) {
        const lower = m.name.toLowerCase();
        if (lower.indexOf('winble') !== -1 || lower.indexOf('mfcontrol') !== -1 ||
            lower.indexOf('mfdevice') !== -1 || lower.indexOf('mffound') !== -1 ||
            lower.indexOf('bthprops') !== -1 || lower.indexOf('bluetooth') !== -1) {
            interesting.push(m.name + ' @ ' + m.base);
        }
    }
    send({total: mods.length, interesting: interesting});
    """
    script = session.create_script(code)
    result = []
    def on_message(msg, data):
        if msg["type"] == "send":
            result.append(msg["payload"])
    script.on("message", on_message)
    script.load()
    import time; time.sleep(1)
    if result:
        r = result[0]
        print(f"  total modules: {r['total']}")
        print("  interesting:")
        for x in r["interesting"]:
            print(f"    {x}")
    session.detach()


for p in PROCESSES:
    check_process(p)
