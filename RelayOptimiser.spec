# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build spec for the Swimming Relay Optimiser GUI.

Build with:   pyinstaller --noconfirm RelayOptimiser.spec
Output:       dist/Relay Optimiser.exe  (a single double-clickable Windows app)
"""
from PyInstaller.utils.hooks import collect_all

# Bundle the records database next to the app (read via sys._MEIPASS at runtime).
datas = [("data/records.json", "data")]
binaries = []
hiddenimports = [
    # src/ modules -- imported after a sys.path.insert, so list them explicitly
    "models", "config", "record_fetcher", "age_category", "relay_builder",
    "scorer", "optimiser", "reporter", "timefmt", "relay_eval", "relay_gui",
]

# PuLP ships the CBC solver binary as package data -- pull it all in.
for _pkg in ("pulp",):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    ["main.py"],
    pathex=["src"],            # so the src/ modules resolve during analysis
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Relay Optimiser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,             # no terminal window -- pure GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    # icon="data/icon.ico",    # add an .ico here if you want a custom icon
)
