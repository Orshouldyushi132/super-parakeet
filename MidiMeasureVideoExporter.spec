# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, copy_metadata


imageio_datas, imageio_binaries, imageio_hiddenimports = collect_all("imageio")
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all("imageio_ffmpeg")

datas = []
datas += imageio_datas
datas += ffmpeg_datas
datas += copy_metadata("imageio")
datas += copy_metadata("imageio-ffmpeg")

binaries = []
binaries += imageio_binaries
binaries += ffmpeg_binaries

hiddenimports = []
hiddenimports += imageio_hiddenimports
hiddenimports += ffmpeg_hiddenimports
hiddenimports += ["PIL._tkinter_finder"]


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MidiMeasureVideoExporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MidiMeasureVideoExporter",
)
