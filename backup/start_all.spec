# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['start_all.py'],
    pathex=[],
    binaries=[('/usr/local/Cellar/opus/1.5.2/lib/libopus.0.dylib', '.')],
    datas=[('certs', 'certs'), ('config_dialog.py', '.'), ('LOOPS', 'LOOPS')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='start_all',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo2.icns'],
)
