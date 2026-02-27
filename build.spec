# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# 需要打包的数据文件
datas = [
    ('icon.ico', '.'),  # 图标文件
]

# 如果存在 libmpv-2.dll，也要打包进去
import os
if os.path.exists('libmpv-2.dll'):
    datas.append(('libmpv-2.dll', '.'))

# 需要的隐藏导入
hiddenimports = [
    'mpv',
    'darkdetect',
    'qtawesome',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.sip',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 一目录模式（one-dir）：EXE 不包含数据文件，由 COLLECT 统一打包到输出目录
# 相比单文件模式（one-file），一目录模式不需要每次启动时解压到临时目录，
# 更稳定、不会被杀毒软件误杀，也不会出现临时目录冲突导致打不开的问题。
exe = EXE(
    pyz,
    a.scripts,
    [],
    name='视频播放器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',  # 设置程序图标
)

# 收集所有文件到输出目录（dist/视频播放器/）
# PyInstaller 6+ 会将依赖放入 _internal/ 子目录
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='视频播放器',
)
