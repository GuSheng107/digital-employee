#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v uv >/dev/null 2>&1 || {
  echo "[ERROR] 未找到 uv，请先安装: https://docs.astral.sh/uv/" >&2
  exit 1
}

exec uv run python "$SCRIPT_DIR/start-all.py"
