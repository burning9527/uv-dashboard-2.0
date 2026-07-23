#!/bin/bash
# UV Dashboard 2.0 一键启动（用于本机真实终端，非 WorkBuddy 对话内）
# 用法：
#   chmod +x start_uv2.sh
#   ./start_uv2.sh
# 推荐改用 launchd 常驻（见下方说明），此脚本用于临时启动。

DIR="/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard-2.0"
PY="/Users/wangboning/.workbuddy/binaries/python/envs/default/bin/python"

cd "$DIR" || exit 1
nohup "$PY" app.py > /tmp/uv2.log 2>&1 &
echo "UV Dashboard 2.0 已启动, PID $! -> http://localhost:5200"
echo "日志: /tmp/uv2.log"

# ─────────────────────────────────────────────────────────────
# 想彻底免维护（登录自启 + 崩溃自动重启 + 关对话不掉）？
# 在本机「终端」App 执行下面一行即可（plist 已备好在 ~/Library/LaunchAgents/）：
#   launchctl load -w ~/Library/LaunchAgents/com.uv.dashboard2.plist
# 停用：launchctl unload ~/Library/LaunchAgents/com.uv.dashboard2.plist
# ─────────────────────────────────────────────────────────────
