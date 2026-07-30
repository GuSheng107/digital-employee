#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT_DIR="$REPO_ROOT/backend-data"
PID_FILE="$ROOT_DIR/run/backend.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "data platform backend is not running: pid file not found"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "stopped data platform backend, pid=$PID"
else
  echo "data platform backend process is not running, stale pid=$PID"
fi

rm -f "$PID_FILE"
