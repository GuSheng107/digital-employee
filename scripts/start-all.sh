#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

command -v uv >/dev/null 2>&1 || {
  echo "[ERROR] 未找到 uv，请先安装: https://docs.astral.sh/uv/" >&2
  exit 1
}

# 健康检查轮询：等待指定 URL 返回 2xx，超时后打 warning 但不阻断后续步骤
# （服务可能因依赖缺失启动失败，由用户根据日志排查）
wait_for_health() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-15}"
  local attempt=0
  while (( attempt < max_attempts )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[OK] $name 已就绪"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  echo "[WARN] $name 在 $((max_attempts * 2))s 内未就绪，请查看日志排查"
  return 1
}

echo "==================================================="
echo "  Digital Employee - 一键启动所有服务"
echo "==================================================="
echo ""

echo "[INFO] 步骤 1/4: 清理全项目 Python 缓存..."
uv run python "$SCRIPT_DIR/clean-pycache.py" || true
echo ""

echo "[INFO] 步骤 2/4: 启动 Backend Gateway 网关服务 (8864)..."
if [ -f "$SCRIPT_DIR/backend-gateway/start.sh" ]; then
    bash "$SCRIPT_DIR/backend-gateway/start.sh" &
    GATEWAY_PID=$!
    echo "Backend Gateway shell PID: $GATEWAY_PID"
    wait_for_health "Backend Gateway" "http://localhost:8864/api/v1/health" 10 || true
fi

echo "[INFO] 步骤 3/4: 启动 Backend Data 数据中台服务 (8010)..."
if [ -f "$SCRIPT_DIR/data-platform/start.sh" ]; then
    bash "$SCRIPT_DIR/data-platform/start.sh" &
    # 注意：data-platform/start.sh 内部用 nohup 后台启动 uvicorn 后立即退出，
    # 此处 $! 是 bash 子 shell PID 而非 uvicorn 进程 PID，仅用于 start-all 退出码跟踪
    DATA_SHELL_PID=$!
    echo "Backend Data shell PID: $DATA_SHELL_PID"
    wait_for_health "Backend Data" "http://localhost:8010/api/v1/health" 15 || true
fi

echo "[INFO] 步骤 4/4: 启动 Frontend 前端开发服务 (5173)..."
bash "$SCRIPT_DIR/frontend/start-web.sh" &
FRONTEND_PID=$!
echo "Frontend Dev Server PID: $FRONTEND_PID"

echo ""
echo "==================================================="
echo "  所有后台服务已拉起！"
echo "  - Backend Gateway: http://localhost:8864"
echo "  - Backend Data:    http://localhost:8010"
echo "  - Frontend Dev:    http://localhost:5173"
echo "==================================================="
