# -*- mode: python ; coding: utf-8 -*-
# Compilar con:  pyinstaller ascenso.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = [("assets", "assets")] + collect_data_files("mediapipe")
binaries = collect_dynamic_libs("mediapipe")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pyttsx3.drivers", "pyttsx3.drivers.sapi5", "comtypes.client"],
    excludes=["jax", "jaxlib", "tensorflow", "torch", "scipy", "sounddevice", "tkinter",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick3D"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Ascenso",
    icon="assets/icon.ico",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Ascenso")
