# PyInstaller spec for poof-ble-check — tiny standalone tool that checks
# whether the host BT adapter supports BLE peripheral role.

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve()
BACKEND = PROJECT_ROOT / "backend"

# winsdk loads bluetooth/enumeration modules dynamically.
hiddenimports = collect_submodules("winsdk")

excludes = [
    "PySide6", "shiboken6", "tkinter", "matplotlib", "numpy",
    "pymobiledevice3", "dbus_next",
]


a = Analysis(
    [str(BACKEND / "check_ble_peripheral.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=[],
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
    name="poof-ble-check",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
