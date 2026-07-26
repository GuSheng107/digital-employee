#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT_DIR="$REPO_ROOT/digital-employee-data-platform"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"
PID_FILE="$ROOT_DIR/run/backend.pid"

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

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "process=running pid=$(cat "$PID_FILE")"
else
  echo "process=stopped"
fi

if command -v curl >/dev/null 2>&1; then
  echo "health=http://${APP_HOST}:${APP_PORT}/health"
  curl -fsS "http://${APP_HOST}:${APP_PORT}/health" || true
  echo
else
  echo "curl is not installed; skip health request"
fi
