# -*- mode: python; coding: utf-8 -*-
"""PyInstaller build spec for ZeroTraceFXAI.exe (Windows, windowed dashboard)."""
import os

block_cipher = None
ROOT = os.path.abspath(SPECCWD)
ICON = os.path.join(ROOT, "assets", "app.ico")

datas = [
    (os.path.join(ROOT, ".env.example"), "."),
    (os.path.join(ROOT, "assets"), "assets"),
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pandas", "numpy", "pydantic", "pydantic_settings", "dotenv",
        "aiohttp", "matplotlib", "MetaTrader5", "PySide6",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "notebook"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ZeroTraceFXAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed: launches the dashboard directly
    icon=ICON if os.path.exists(ICON) else None,
    version=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, name="ZeroTraceFXAI",
)
