# PyInstaller spec for poof — iOS Location Spoofer GUI.
#
# Build from the project root:
#     backend\.venv\Scripts\pyinstaller.exe poof.spec --clean
#
# Output: dist/poof.exe (onefile, windowed). Onefile makes for a clean "send
# to a friend" experience but slower first-launch (~10-20 s) since the bundle
# self-extracts to %TEMP%. Switch `onefile=False` below for a faster-starting
# folder build if needed later.

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve()
BACKEND = PROJECT_ROOT / "backend"

# ---- Resource data ---------------------------------------------------
# Map.html + Leaflet + marker pngs must travel with the .exe.
datas = [
    (str(BACKEND / "gui" / "assets" / "map.html"), "backend/gui/assets"),
    (str(BACKEND / "gui" / "assets" / "leaflet"), "backend/gui/assets/leaflet"),
]

# ---- Hidden imports --------------------------------------------------
# pymobiledevice3 uses pkg-style dynamic submodule loading, so PyInstaller's
# static analysis misses a lot. Just pull all of it in.
hiddenimports = collect_submodules("pymobiledevice3")

# pymobiledevice3 ships some data files (DDI configs, plist templates).
datas += collect_data_files("pymobiledevice3")

# pytun_pmd3 ships native wintun DLLs inside its package — PyInstaller's static
# analysis misses them. Needed even from the GUI in case it ever talks to
# tunneld via the same process (currently doesn't, but bundling is safe).
hiddenimports += collect_submodules("pytun_pmd3")
datas += collect_data_files("pytun_pmd3")
hiddenimports += collect_submodules("qh3")

# winsdk is also dynamically-loaded; pull all of it under
# winsdk.windows.devices.bluetooth.* in case we wire WinRT later.
hiddenimports += collect_submodules("winsdk")

# These are usually fine but list them explicitly to be safe.
hiddenimports += [
    "cryptography",
    "cryptography.hazmat.bindings._rust",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
]

# winsdk specific submodules used by our BLE peripheral.
# collect_submodules misses these because winsdk uses dynamic native loaders.
hiddenimports += [
    "winsdk.windows.devices.bluetooth",
    "winsdk.windows.devices.bluetooth.advertisement",
    "winsdk.windows.devices.bluetooth.genericattributeprofile",
    "winsdk.windows.devices.enumeration",
    "winsdk.windows.devices.radios",
    "winsdk.windows.storage.streams",
    "winsdk.windows.foundation",
    "winsdk.windows.foundation.collections",
]
# Be doubly sure: pull all winsdk binaries too.
from PyInstaller.utils.hooks import collect_dynamic_libs
binaries_extra = collect_dynamic_libs("winsdk")

# ---- Excludes --------------------------------------------------------
# dbus-next is Linux-only at runtime. PyInstaller may try to bundle it but
# it has no use on Windows; excluding shaves a few MB.
excludes = ["dbus_next"]


a = Analysis(
    [str(BACKEND / "gui" / "main.py")],
    pathex=[str(BACKEND)],
    binaries=binaries_extra,
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
    name="poof",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX often trips antivirus heuristics — leave the binary as-is
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # windowed mode — no stray console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
