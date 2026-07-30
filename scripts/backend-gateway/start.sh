#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT/backend-gateway"

command -v uv >/dev/null 2>&1 || {
  echo "[ERROR] 未找到 uv，请先安装: https://docs.astral.sh/uv/" >&2
  exit 1
}

echo "[INFO] 项目根目录: $PROJECT_ROOT"
echo "[INFO] 启动网关服务 (uv run uvicorn src.main:app)..."
echo "  - 本地访问: http://localhost:8864"
echo "  - 健康检查: http://localhost:8864/api/v1/health"
echo ""

cd "$PROJECT_ROOT"
exec uv run uvicorn src.main:app --host 0.0.0.0 --port 8864 "$@"
