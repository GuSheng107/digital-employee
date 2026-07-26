#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT_DIR="$REPO_ROOT/backend-data"
BACKEND_DIR="$ROOT_DIR/backend"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
ENV_FILE="$BACKEND_DIR/.env"
PID_FILE="$RUN_DIR/backend.pid"

get_env() {
  local key="$1"
  local default_value="$2"
  if [[ -f "$ENV_FILE" ]]; then
    local value
    value="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d '=' -f 2- | tr -d '\r' || true)"
    if [[ -n "$value" ]]; then
      printf '%s' "$value"
      return
    fi
  fi
  printf '%s' "$default_value"
}

APP_HOST="${APP_HOST:-$(get_env APP_HOST 127.0.0.1)}"
APP_PORT="${APP_PORT:-$(get_env APP_PORT 8010)}"

mkdir -p "$LOG_DIR" "$RUN_DIR"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "data platform backend is already running, pid=$(cat "$PID_FILE")"
  exit 0
fi

cd "$BACKEND_DIR"
nohup uv run uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT" \
  > "$LOG_DIR/backend.log" 2>&1 &
echo "$!" > "$PID_FILE"

echo "data platform backend started"
echo "pid=$(cat "$PID_FILE")"
echo "url=http://${APP_HOST}:${APP_PORT}"
echo "log=$LOG_DIR/backend.log"
