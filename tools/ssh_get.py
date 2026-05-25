"""Download a file from planshet to stationary via SFTP."""

from __future__ import annotations

import sys
import paramiko


HOST = "192.168.0.200"
USER = "Venue"
PASSWORD = "1234"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: ssh_get.py <remote> <local>", file=sys.stderr)
        return 1
    remote, local = sys.argv[1], sys.argv[2]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15,
                   allow_agent=False, look_for_keys=False)
    sftp = client.open_sftp()
    sftp.get(remote, local)
    sftp.close()
    client.close()
    print(f"OK: {HOST}:{remote} -> {local}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
