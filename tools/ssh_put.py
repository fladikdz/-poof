"""Copy a file from stationary to planshet via SFTP.

Usage:
    python ssh_put.py <local-file> <remote-path>
"""

from __future__ import annotations

import sys

import paramiko


HOST = "192.168.0.200"
USER = "Venue"
PASSWORD = "1234"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: ssh_put.py <local> <remote>", file=sys.stderr)
        return 1
    local, remote = sys.argv[1], sys.argv[2]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15,
                   allow_agent=False, look_for_keys=False)
    sftp = client.open_sftp()
    sftp.put(local, remote)
    sftp.close()
    client.close()
    print(f"OK: {local} -> {HOST}:{remote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
