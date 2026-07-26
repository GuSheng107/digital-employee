#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT/backend-agent"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "[ERROR] Python 虚拟环境不存在: $PYTHON"
    echo "请先在 backend-agent 目录下安装依赖 (uv sync)。"
    exit 1
fi

echo "[INFO] 项目根目录: $PROJECT_ROOT"
echo ""

echo "[INFO] 步骤 1/2: 清理 __pycache__ 目录..."
"$PYTHON" "$SCRIPT_DIR/../clean-pycache.py" || echo "[WARN] 清理过程遇到警告，继续执行..."
echo ""

echo "[INFO] 步骤 2/2: 启动 backend-agent 服务..."
cd "$PROJECT_ROOT"
"$PYTHON" "$PROJECT_ROOT/main.py" --project-root "$PROJECT_ROOT"
