# PyInstaller spec for poof-tunneld — separate console .exe that runs the
# pymobiledevice3 tunneld server (iOS 17+ DVT prerequisite).
#
# Build:
#     backend\.venv\Scripts\pyinstaller.exe poof-tunneld.spec --clean --noconfirm
#
# Output: dist/poof-tunneld.exe (console). Must be launched with admin rights —
# Inno Setup shortcut will set "Run as administrator" on it.

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve()
BACKEND = PROJECT_ROOT / "backend"

# Only pymobiledevice3 + its data files; no PySide6/QtWebEngine here, so this
# .exe is much smaller than the GUI one.
hiddenimports = collect_submodules("pymobiledevice3")
datas = collect_data_files("pymobiledevice3")

# pytun_pmd3 ships native wintun DLLs inside its package — PyInstaller's static
# analysis misses them. Without this the tunneld errors at startup with
# "Failed to load pytun_pmd3/wintun/bin/amd64/wintun.dll".
hiddenimports += collect_submodules("pytun_pmd3")
datas += collect_data_files("pytun_pmd3")

# qh3 (QUIC/HTTP3 used by remoted) has compiled extensions too.
hiddenimports += collect_submodules("qh3")

excludes = [
    "PySide6", "shiboken6",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel", "PySide6.QtWidgets",
    "tkinter", "matplotlib", "numpy",
    "dbus_next",
]


a = Analysis(
    [str(BACKEND / "start_tunneld.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="poof-tunneld",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # console mode — user sees tunneld log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
