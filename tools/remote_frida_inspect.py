"""Attach Frida to AnyTo and run an inspection script."""

from __future__ import annotations

import sys
from pathlib import Path

import frida


def main() -> int:
    script_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "frida_inspect.js"
    code = script_path.read_text(encoding="utf-8")

    session = frida.attach("AnyTo.exe")
    script = session.create_script(code)
    def on_message(message, data):
        if message["type"] == "send":
            print(message["payload"])
        elif message["type"] == "error":
            print("FRIDA ERROR:", message.get("stack") or message.get("description"), file=sys.stderr)
    script.on("message", on_message)
    script.load()
    # Wait briefly for output to drain
    import time
    time.sleep(2)
    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
