#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "  Digital Employee Starting..."
echo "========================================"
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_ROOT/backend-agent/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "[ERROR] Python virtual environment not found: $PYTHON"
  echo "Please install dependencies first:"
  echo "  cd backend-agent"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -e '.[dev]'"
  exit 1
fi

echo "[INFO] Project root: $PROJECT_ROOT"
echo

echo "[INFO] Step 1/2: Cleaning __pycache__ directories..."
"$PYTHON" "$SCRIPT_DIR/clean-pycache.py" || {
  echo "[WARN] Cleanup encountered an error, continuing anyway..."
}
echo

echo "[INFO] Step 2/2: Starting backend-agent service..."
echo "  - Local access: http://localhost:8765"

lan_ips=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' || true)
if [ -n "$lan_ips" ]; then
  echo "  - LAN access:"
  echo "$lan_ips" | while read -r ip; do
    echo "    http://$ip:8765"
  done
else
  echo "  - LAN access: (no LAN IP detected)"
fi
echo

cd "$PROJECT_ROOT/backend-agent"
"$PYTHON" "$PROJECT_ROOT/backend-agent/main.py" --project-root "$PROJECT_ROOT/backend-agent"

exit_code=$?
if [ $exit_code -ne 0 ]; then
  echo
  echo "[ERROR] Program exited with error code: $exit_code"
  echo "Press Enter to exit..."
  read -r
fi
