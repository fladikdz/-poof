"""Resolve runtime paths in a way that works both in dev (running from source)
and in PyInstaller-frozen builds.

Three categories of paths:

  - **Bundled resources** — read-only files that ship with the app (map.html,
    leaflet/*, default icon). In dev they live next to the source files; in a
    PyInstaller onefile build they're unpacked to a temp dir reachable via
    `sys._MEIPASS`. Use `resource_path(...)`.

  - **User data** — writable per-user files: PGP master key, session cert.
    These must NOT live next to the .exe (Program Files is read-only for
    non-admin users) so we put them in `%APPDATA%/poof` on Windows,
    `~/.local/share/poof` on Linux, `~/Library/Application Support/poof` on
    macOS. Use `user_data_path(...)`.

  - **Logs** — same idea as user data but in a `logs/` subdirectory. Use
    `user_log_path(...)`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundle_root() -> Path:
    """The directory PyInstaller unpacks resources into, or the source root in dev."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # Dev mode: source root is the parent of `backend/`. We're in backend/core/.
    return Path(__file__).resolve().parent.parent.parent


def resource_path(*parts: str) -> Path:
    """Return a path to a bundled read-only resource.

    Example: `resource_path("backend", "gui", "assets", "map.html")`.
    """
    return _bundle_root().joinpath(*parts)


def user_data_dir() -> Path:
    """OS-specific writable directory for user data. Created if missing."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    out = base / "poof"
    out.mkdir(parents=True, exist_ok=True)
    return out


def user_data_path(*parts: str) -> Path:
    """Return a path inside the per-user writable data dir."""
    p = user_data_dir().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def user_log_dir() -> Path:
    out = user_data_dir() / "logs"
    out.mkdir(parents=True, exist_ok=True)
    return out
