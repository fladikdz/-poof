"""Recursively copy a local directory to planshet via SFTP."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko


HOST = "192.168.0.200"
USER = "Venue"
PASSWORD = "1234"


def _mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.replace("\\", "/").strip("/").split("/")
    cur = ""
    for p in parts:
        cur = cur + "/" + p if cur else p
        if len(cur) == 2 and cur[1] == ":":   # drive root like "C:"
            continue
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: ssh_put_dir.py <local-dir> <remote-dir>", file=sys.stderr)
        return 1
    local = Path(sys.argv[1]).resolve()
    remote_root = sys.argv[2].rstrip("/")
    if not local.is_dir():
        print(f"Local dir not found: {local}", file=sys.stderr)
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15,
                   allow_agent=False, look_for_keys=False)
    sftp = client.open_sftp()
    _mkdir_p(sftp, remote_root)

    n = 0
    for src in local.rglob("*"):
        if src.is_dir():
            rel = src.relative_to(local).as_posix()
            _mkdir_p(sftp, f"{remote_root}/{rel}")
            continue
        if src.suffix in (".pyc",) or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(local).as_posix()
        dst = f"{remote_root}/{rel}"
        # ensure parent exists
        _mkdir_p(sftp, dst.rsplit("/", 1)[0])
        sftp.put(str(src), dst)
        n += 1
    print(f"OK: copied {n} files from {local} -> {HOST}:{remote_root}")
    sftp.close()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
