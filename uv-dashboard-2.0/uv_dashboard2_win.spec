# -*- mode: python ; coding: utf-8 -*-
# UV Dashboard 2.0 — Windows .exe 打包配置
#
# 使用方法（在 Windows 上）：
#   1. 安装 Python 3.13+ 和依赖：pip install -r requirements.txt
#   2. 安装 PyInstaller：pip install pyinstaller
#   3. 运行：pyinstaller uv_dashboard2_win.spec --noconfirm
#   4. 产物在 dist\UV Dashboard 2.0\ 目录下
#
# 注意：PyInstaller 不支持跨平台编译，必须在 Windows 上运行此 spec。

import os
import sys

block_cipher = None

# Windows 上用 __file__ 定位，不硬编码路径
PROJECT_DIR = os.path.dirname(os.path.abspath(SPEC))

# 动态构建 datas 列表（容错：db 文件可能不存在，如 CI 构建时）
_datas = [
    (os.path.join(PROJECT_DIR, 'templates'), 'templates'),
    (os.path.join(PROJECT_DIR, 'static', 'css'), 'static/css'),
    (os.path.join(PROJECT_DIR, 'static', 'js'), 'static/js'),
]
_db_path = os.path.join(PROJECT_DIR, 'uv_dashboard.db')
if os.path.exists(_db_path):
    _datas.append((_db_path, '.'))
else:
    print(f'[WARN] uv_dashboard.db not found at {_db_path} — app will create empty DB on first run')

a = Analysis(
    [os.path.join(PROJECT_DIR, 'app.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'flask',
        'werkzeug',
        'jinja2',
        'markupsafe',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'openpyxl.cell',
        'openpyxl.workbook',
        'openpyxl.worksheet',
        'openpyxl.reader',
        'openpyxl.writer',
        'et_xmlfile',
        'lxml',
        'lxml._elementpath',
        'lxml.etree',
        'sqlite3',
        'config',
        'engine',
        'engine.calibrator',
        'engine.order_detail_loader',
        'repository',
        'exporter',
        'api',
        'webbrowser',
        'numpy',
        'dateutil',
        'dateutil.parser',
        'dateutil.relativedelta',
        'PIL',
        'xlsxwriter',
        'numpy',
        # ── pywebview Windows backend ──
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'webview.util',
        'webview.event',
        'webview.menu',
        'webview.state',
        'webview.dom',
        'webview.errors',
        'webview.http',
        'webview.screen',
        'proxy_tools',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'scipy', 'IPython',
        'notebook', 'pyngrok', 'pikepdf', 'pymupdf',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx',
        'django', 'tornado', 'setuptools', 'pip', 'wheel',
        'pandas',
        # macOS only
        'webview.platforms.cocoa',
        'webview.platforms.gtk',
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
    name='UV Dashboard 2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不弹终端窗口
    icon=os.path.join(PROJECT_DIR, 'build_assets', 'build_assets', 'AppIcon.ico'),
    uac_admin=False,  # 不需要管理员权限
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UV Dashboard 2.0',
)
