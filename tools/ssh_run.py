"""Run a command on the plansшет via SSH and print stdout/stderr.

Usage:
    python ssh_run.py "<command-or-script>"
    cat script.ps1 | python ssh_run.py "powershell -Command -"

Hardcodes the planshet IP / user / password for convenience during debugging.
"""

from __future__ import annotations

import sys

import paramiko


HOST = "192.168.0.200"
USER = "Venue"
PASSWORD = "1234"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: ssh_run.py '<command>'", file=sys.stderr)
        return 1
    cmd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=15, allow_agent=False, look_for_keys=False)
    except Exception as exc:
        print(f"SSH connect failed: {exc}", file=sys.stderr)
        return 2

    stdin, stdout, stderr = client.exec_command(cmd, timeout=120, get_pty=False)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    if out:
        print(out, end="")
    if err:
        print("--- stderr ---", file=sys.stderr)
        print(err, end="", file=sys.stderr)
    client.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
