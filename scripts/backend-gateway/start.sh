#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT/backend-gateway"

echo "[INFO] 项目根目录: $PROJECT_ROOT"
echo "[INFO] 启动网关服务 (uv run python -m src.main)..."
echo "  - 本地访问: http://localhost:8864"
echo ""

cd "$PROJECT_ROOT"
exec uv run python -m src.main "$@"
