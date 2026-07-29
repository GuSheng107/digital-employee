#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT/backend-auth"

command -v uv >/dev/null 2>&1 || {
  echo "[ERROR] 未找到 uv，请先安装: https://docs.astral.sh/uv/" >&2
  exit 1
}

if [[ ! -f "$PROJECT_ROOT/.env" && -f "$PROJECT_ROOT/.env.example" ]]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
fi

echo "[INFO] 启动认证服务 (http://localhost:8020)..."
cd "$PROJECT_ROOT"
exec uv run uvicorn app.main:app --host 127.0.0.1 --port 8020 "$@"
