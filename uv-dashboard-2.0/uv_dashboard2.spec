# -*- mode: python ; coding: utf-8 -*-
# UV Dashboard 2.0 — macOS .app 打包配置

import os
import sys

block_cipher = None

PROJECT_DIR = '/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard-2.0'

a = Analysis(
    [os.path.join(PROJECT_DIR, 'app.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        # 模板文件
        (os.path.join(PROJECT_DIR, 'templates'), 'templates'),
        # 静态资源 — CSS
        (os.path.join(PROJECT_DIR, 'static', 'css'), 'static/css'),
        # 静态资源 — JS
        (os.path.join(PROJECT_DIR, 'static', 'js'), 'static/js'),
        # 内置数据库（首次启动拷贝到 ~/Library/Application Support/UV Dashboard 2.0/）
        (os.path.join(PROJECT_DIR, 'uv_dashboard.db'), '.'),
    ],
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
        # ── pywebview（独立 app 窗口，不打开浏览器）──
        'webview',
        'webview.platforms.cocoa',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'webview.platforms.gtk',
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
        'pandas',  # 不直接使用，排除以减小体积
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
    console=False,
    icon=os.path.join(PROJECT_DIR, 'build_assets', 'build_assets', 'AppIcon.icns'),
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

app = BUNDLE(
    coll,
    name='UV Dashboard 2.0.app',
    icon=os.path.join(PROJECT_DIR, 'build_assets', 'build_assets', 'AppIcon.icns'),
    bundle_identifier='com.uv.dashboard2',
    version='2.0.0',
    info_plist={
        'CFBundleName': 'UV Dashboard 2.0',
        'CFBundleDisplayName': 'UV台帐管理系统 2.0',
        'CFBundleVersion': '2.0.0',
        'CFBundleShortVersionString': '2.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'CFBundleIdentifier': 'com.uv.dashboard2',
        'LSBackgroundOnly': False,
        'NSAppTransportSecurity': {
            'NSAllowsArbitraryLoads': True,
        },
    },
)
