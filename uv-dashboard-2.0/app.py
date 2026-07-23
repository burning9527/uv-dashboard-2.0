"""
UV Dashboard 2.0 — 应用入口
初始化 Flask app，注册 Blueprint，启动服务器。
FROZEN 模式（PyInstaller 打包）用 pywebview 嵌入系统 WebView（macOS WKWebView），
不再打开浏览器，而是独立 app 窗口。
"""

import sys
import os
import threading

# ── 路径设置 ──
FROZEN = getattr(sys, 'frozen', False)

if FROZEN:
    # PyInstaller 打包模式：资源（templates/static）在 _MEIPASS 中
    RESOURCE_DIR = sys._MEIPASS
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))

# 确保模块目录在 sys.path 中
if RESOURCE_DIR not in sys.path:
    sys.path.insert(0, RESOURCE_DIR)

from flask import Flask, render_template

from config import DEFAULT_PORT
from repository import set_data_dir, init_db
from api import overview_bp, calibration_bp, share_bp


def create_app(data_dir=None):
    """创建 Flask 应用"""
    app = Flask(__name__,
                template_folder=os.path.join(RESOURCE_DIR, 'templates'),
                static_folder=os.path.join(RESOURCE_DIR, 'static'))

    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

    # ── 数据目录 ──
    if data_dir is None:
        if FROZEN:
            # PyInstaller 打包模式：使用 2.0 独立目录（与 1.0 物理隔离）
            if sys.platform == 'win32':
                data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                                        'UV Dashboard 2.0')
            else:
                data_dir = os.path.expanduser('~') + '/Library/Application Support/UV Dashboard 2.0'
            os.makedirs(data_dir, exist_ok=True)
            # 首次启动：若数据目录无数据库，从打包资源拷贝内置数据库
            bundled_db = os.path.join(RESOURCE_DIR, 'uv_dashboard.db')
            target_db = os.path.join(data_dir, 'uv_dashboard.db')
            if os.path.exists(bundled_db) and not os.path.exists(target_db):
                import shutil
                shutil.copy2(bundled_db, target_db)
                print(f'已初始化内置数据库 → {target_db}')
        else:
            # 开发模式：使用 2.0 独立数据库（与 1.0 完全分离）
            data_dir = RESOURCE_DIR

    set_data_dir(data_dir)
    init_db()

    # ── 注册 Blueprint ──
    app.register_blueprint(overview_bp)
    app.register_blueprint(calibration_bp)
    app.register_blueprint(share_bp)

    # ── 主页面 ──
    @app.route('/')
    def index():
        return render_template('index.html')

    return app


def _run_flask(app, port):
    """后台线程：跑 Flask（debug=False 不重载）"""
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)


def main():
    """启动服务器"""
    app = create_app()
    port = int(os.environ.get('UV_PORT', DEFAULT_PORT))

    if FROZEN:
        # 打包模式：用 pywebview 嵌入系统 WebView（独立 app 窗口，不是浏览器）
        import time
        import webview

        # 后台线程跑 Flask
        flask_thread = threading.Thread(target=_run_flask, args=(app, port), daemon=True)
        flask_thread.start()

        # 等 Flask 启动
        import urllib.request
        url = f'http://127.0.0.1:{port}/'
        for _ in range(30):
            try:
                urllib.request.urlopen(url, timeout=0.5)
                break
            except Exception:
                time.sleep(0.2)

        # 主线程：创建独立 app 窗口（macOS WKWebView）
        # frameless=True 去掉系统标题栏（更像原生 app，不像浏览器）
        # easy_drag=True 允许拖动自定义标题栏区域
        # text_select=False 禁止文本选择（app 风格）
        # zoomable=False 禁止页面缩放
        window = webview.create_window(
            title='UV台帐管理系统',
            url=url,
            width=1400,
            height=900,
            min_size=(1000, 600),
            resizable=True,
            frameless=False,
            easy_drag=True,
            text_select=False,
            zoomable=False,
        )

        # 注入 CSS 隐藏滚动条 + 禁止右键菜单（更像 app）
        def _on_loaded():
            window.evaluate_js("""
                document.documentElement.style.scrollbarWidth = 'thin';
                document.addEventListener('contextmenu', e => e.preventDefault());
                document.body.style.webkitUserSelect = 'none';
                document.body.style.webkitTapHighlightColor = 'transparent';
            """)

        window.events.loaded += _on_loaded
        webview.start()
    else:
        # 开发模式：保持原行为（debug server, 可手动访问 http://localhost:port/）
        print(f'UV Dashboard 2.0 启动端口: {port}  http://localhost:{port}')
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)


if __name__ == '__main__':
    main()
