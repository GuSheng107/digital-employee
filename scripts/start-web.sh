#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$REPO_ROOT/frontend/package.json" ]; then
    echo "[ERROR] 前端项目文件未找到: $REPO_ROOT/frontend/package.json"
    exit 1
fi

cd "$REPO_ROOT/frontend"
echo "[INFO] 切换至前端目录: $REPO_ROOT/frontend"

if [ ! -d "$REPO_ROOT/frontend/node_modules" ]; then
    echo "[INFO] node_modules 不存在，自动运行 npm install..."
    npm install
fi

echo "[INFO] 正在执行 npm run dev 启动开发服务 (http://localhost:5173)..."
echo ""

exec npm run dev "$@"
