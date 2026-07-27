#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

command -v uv >/dev/null 2>&1 || {
  echo "[ERROR] 未找到 uv，请先安装: https://docs.astral.sh/uv/" >&2
  exit 1
}

echo "==================================================="
echo "  Digital Employee - 一键启动所有服务"
echo "==================================================="
echo ""

echo "[INFO] 步骤 1/5: 清理全项目 Python 缓存..."
uv run python "$SCRIPT_DIR/clean-pycache.py" || true
echo ""

echo "[INFO] 步骤 2/5: 启动 Backend Agent 服务 (8765)..."
bash "$SCRIPT_DIR/backend-agent/start.sh" &
AGENT_PID=$!
echo "Backend Agent PID: $AGENT_PID"

echo "[INFO] 步骤 3/5: 启动 Backend Gateway 网关服务 (8864)..."
if [ -f "$SCRIPT_DIR/backend-gateway/start.sh" ]; then
    bash "$SCRIPT_DIR/backend-gateway/start.sh" &
    GATEWAY_PID=$!
    echo "Backend Gateway PID: $GATEWAY_PID"
fi

echo "[INFO] 步骤 4/5: 启动 Backend Data 服务 (8010)..."
if [ -f "$SCRIPT_DIR/data-platform/start.sh" ]; then
    bash "$SCRIPT_DIR/data-platform/start.sh" &
    DATA_PID=$!
    echo "Backend Data PID: $DATA_PID"
fi

echo "[INFO] 步骤 5/5: 启动 Frontend 前端开发服务 (5173)..."
bash "$SCRIPT_DIR/frontend/start-web.sh" &
FRONTEND_PID=$!
echo "Frontend Dev Server PID: $FRONTEND_PID"

echo ""
echo "==================================================="
echo "  所有后台服务已拉起！"
echo "  - Backend Agent:   http://localhost:8765"
echo "  - Backend Gateway: http://localhost:8864"
echo "  - Backend Data:    http://localhost:8010"
echo "  - Frontend Dev:    http://localhost:5173"
echo "==================================================="
