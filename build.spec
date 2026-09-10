# -*- mode: python ; coding: utf-8 -*-
# 打包配置（唯一入口）。
# 注意：EXE 名字带中文和 emoji，必须写在 UTF-8 的 .spec 里，
# 不能放到命令行 --name（cmd 用 GBK 读参数会把 emoji 变成乱码）。
# 因此本文件名保持纯 ASCII，构建命令里不出现任何非 ASCII 字符。

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('app/ui', 'ui'), ('app/champions_cache.json', '.'), ('app/augments_cache.json', '.')],
    hiddenimports=['webview.platforms.edgechromium', 'psutil', 'pystray._win32'],
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
    name='恁🐎战绩查询',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app/ui/app-icon.ico'],
)
