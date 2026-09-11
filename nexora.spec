# PyInstaller spec for Windows packaging.
# Build with: pyinstaller nexora.spec
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("nexora")


a = Analysis(
    ["nexora/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
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
    name="NEXORA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
