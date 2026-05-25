"""Run a PowerShell snippet on the planshet via SSH, base64-encoded so no
quoting issues. Returns merged stdout+stderr.

Usage:
    python ssh_ps.py 'Get-Process | Select Name'
    cat script.ps1 | python ssh_ps.py -
"""

from __future__ import annotations

import base64
import sys

import paramiko


HOST = "192.168.0.200"
USER = "Venue"
PASSWORD = "1234"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ssh_ps.py '<ps-script>' OR ssh_ps.py - (read from stdin)", file=sys.stderr)
        return 1

    arg = sys.argv[1]
    if arg == "-":
        script = sys.stdin.read()
    else:
        script = arg

    # PowerShell -EncodedCommand expects UTF-16-LE base64
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = f"powershell -NoProfile -EncodedCommand {enc}"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=15,
                       allow_agent=False, look_for_keys=False)
    except Exception as exc:
        print(f"SSH connect failed: {exc}", file=sys.stderr)
        return 2

    stdin, stdout, stderr = client.exec_command(cmd, timeout=300, get_pty=False)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    sys.stdout.write(out)
    if err:
        sys.stderr.write("--- stderr ---\n")
        sys.stderr.write(err)
    client.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
