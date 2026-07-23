# -*- mode: python ; coding: utf-8 -*-
# UV Dashboard Mac App 打包配置

import os
import sys

block_cipher = None

PROJECT_DIR = '/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard'

a = Analysis(
    [os.path.join(PROJECT_DIR, 'app.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        # 模板文件
        (os.path.join(PROJECT_DIR, 'templates'), 'templates'),
    ],
    hiddenimports=[
        'flask',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'pandas',
        'numpy',
        'sqlite3',
        'calibrator',
        'db',
        'werkzeug',
        'jinja2',
        'markupsafe',
        'PIL',
        'webbrowser',
        'xlsxwriter',
        'lxml',
        'lxml._elementpath',
        'lxml.etree',
        'et_xmlfile',
        'python_dateutil',
        'dateutil',
        'dateutil.parser',
        'dateutil.relativedelta',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'scipy', 'IPython',
        'notebook', 'pyngrok', 'pikepdf', 'pymupdf',
        'PyQt5', 'PyQt6', 'wx', 'django', 'tornado',
        'setuptools', 'pip', 'wheel',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='UV Dashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保持终端窗口以便查看日志
    icon=os.path.join(PROJECT_DIR, 'build_assets', 'AppIcon.icns'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UV Dashboard',
)

app = BUNDLE(
    coll,
    name='UV Dashboard.app',
    icon=os.path.join(PROJECT_DIR, 'build_assets', 'AppIcon.icns'),
    bundle_identifier='com.uv.dashboard',
    version='1.0.0',
    info_plist={
        'CFBundleName': 'UV Dashboard',
        'CFBundleDisplayName': 'UV台帐管理系统',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'CFBundleIdentifier': 'com.uv.dashboard',
    },
)
