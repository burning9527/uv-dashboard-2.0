@echo off
chcp 65001 >nul 2>&1
title UV Dashboard 2.0 — Windows 打包脚本

echo ═══════════════════════════════════════════════════
echo   UV Dashboard 2.0 — Windows .exe 打包脚本
echo ═══════════════════════════════════════════════════
echo.

REM ── 1. 检查 Python ──
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.13+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/4] 检查 Python...
python --version

REM ── 2. 安装依赖 ──
echo.
echo [2/4] 安装依赖包...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM ── 3. 清理旧产物 ──
echo.
echo [3/4] 清理旧构建...
if exist "build" rmdir /s /q "build"
if exist "dist\UV Dashboard 2.0" rmdir /s /q "dist\UV Dashboard 2.0"

REM ── 4. PyInstaller 打包 ──
echo.
echo [4/4] 开始打包（可能需要 2-5 分钟）...
pyinstaller uv_dashboard2_win.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════
echo   打包成功！
echo ═══════════════════════════════════════════════════
echo.
echo 产物路径: dist\UV Dashboard 2.0\UV Dashboard 2.0.exe
echo.
echo 使用方法:
echo   1. 将 dist\UV Dashboard 2.0\ 整个文件夹拷贝到目标机器
echo   2. 双击 UV Dashboard 2.0.exe 启动
echo   3. 首次启动会在 %%APPDATA%%\UV Dashboard 2.0\ 创建数据库
echo.
echo 如需制作安装包，可用 Inno Setup 或 NSIS 打包 dist 目录。
echo.
pause
