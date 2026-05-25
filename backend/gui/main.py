"""Entry point for the GUI.

Run from the project root:
    python backend/gui/main.py

When packaged via PyInstaller, the resulting .exe boots directly into this.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make sibling packages importable when launched as a script
# (so `from core.session import ...` works without setting PYTHONPATH).
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWidgets import QApplication

from gui.app_window import AppWindow


# Real-browser User-Agent — OpenStreetMap tile servers rate-limit / block
# the default QtWebEngine UA (which mentions "QtWebEngine"). Identifying as
# a recent Chrome on Windows avoids the issue and is honest: QtWebEngine
# IS Chromium under the hood.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(name)s  %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("poof")
    app.setOrganizationName("poof")

    # Configure the default web engine profile BEFORE any QWebEngineView is created.
    profile = QWebEngineProfile.defaultProfile()
    profile.setHttpUserAgent(_BROWSER_UA)

    # Dark-ish palette to match the map HUD; Qt's default style on Windows is
    # already light, but stick with system theme — keeps the binary smaller and
    # respects user preferences. We only tweak the status bar / hud explicitly.
    window = AppWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
