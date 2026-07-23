# UV Dashboard 2.0 — Windows 打包指南

## 前提条件

- **Windows 10/11**（64 位）
- **Python 3.13+**（[下载](https://www.python.org/downloads/)，安装时勾选 "Add Python to PATH"）
- 项目源码（整个 `uv-dashboard-2.0/` 文件夹）

## 快速打包

### 方式一：一键脚本（推荐）

1. 将 `uv-dashboard-2.0/` 文件夹拷贝到 Windows 机器
2. 双击运行 `build_windows.bat`
3. 等待 2-5 分钟，产物在 `dist\UV Dashboard 2.0\` 目录

### 方式二：手动命令

```bat
cd uv-dashboard-2.0
pip install -r requirements.txt
pyinstaller uv_dashboard2_win.spec --noconfirm
```

产物路径：`dist\UV Dashboard 2.0\UV Dashboard 2.0.exe`

## 制作安装包（可选）

如果想要一个正式的 `.exe` 安装包（带安装向导、桌面快捷方式、卸载程序）：

1. 下载安装 [Inno Setup](https://jrsoftware.org/isdl.php)（免费）
2. 打开 `installer.iss` 文件
3. 按 `Ctrl+F9` 编译
4. 生成的安装包在 `installer_output\UV-Dashboard-2.0-Setup.exe`

## 产物结构

```
dist\UV Dashboard 2.0\
├── UV Dashboard 2.0.exe    ← 主程序
├── uv_dashboard.db          ← 内置数据库（首次启动拷贝到 %APPDATA%）
├── templates\               ← Flask 模板
├── static\                  ← CSS/JS 静态资源
├── _internal\               ← Python 运行时 + 依赖
└── ...
```

## 用户使用

1. 双击 `UV Dashboard 2.0.exe`（或安装后的桌面快捷方式）
2. 程序自动打开 pywebview 窗口（基于 Edge Chromium WebView2）
3. 首次启动会在 `%APPDATA%\UV Dashboard 2.0\` 创建数据库
4. 数据独立存储，不影响 macOS 版

## 注意事项

- **WebView2 运行时**：Windows 11 自带，Windows 10 可能需要安装 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)（免费）
- **杀毒软件**：PyInstaller 产物可能被误报，需添加信任
- **防火墙**：首次启动可能弹出防火墙提示（Flask 本地端口 5200），选择"允许访问"
- **不跨平台**：PyInstaller 不支持在 macOS 上编译 Windows exe，必须在 Windows 上打包

## 文件清单

| 文件 | 用途 |
|------|------|
| `uv_dashboard2_win.spec` | Windows PyInstaller 配置 |
| `build_windows.bat` | 一键打包脚本 |
| `requirements.txt` | Python 依赖清单 |
| `installer.iss` | Inno Setup 安装包脚本 |
| `build_assets/build_assets/AppIcon.ico` | Windows 图标 |
| `BUILD_WINDOWS.md` | 本文档 |
