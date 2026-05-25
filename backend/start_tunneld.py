"""Run pymobiledevice3 tunneld server without the typer/rich CLI wrapper
(which spews XTGETTCAP escape sequences in Windows PowerShell legacy console).

MUST be run from an Administrator PowerShell — tunneld creates a TUN interface.

Listens on 127.0.0.1:49151 by default (matches pymobiledevice3.tunneld.api).
Leave this window open while using cli_spoof.py from another (non-admin) shell.
"""

from __future__ import annotations

import logging

from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS
from pymobiledevice3.tunneld.server import TunneldRunner


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(name)s  %(message)s")
    host, port = TUNNELD_DEFAULT_ADDRESS
    print(f"Starting tunneld on {host}:{port}  (Ctrl+C to stop)")
    TunneldRunner.create(host, port)


if __name__ == "__main__":
    main()
