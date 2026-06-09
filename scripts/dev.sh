#!/usr/bin/env bash
# Development startup script for digital-employee
set -e

echo "=== Digital Employee Dev Setup ==="

# Start backend-agent
echo "[1/3] Starting backend-agent..."
cd backend-agent
python main.py &
AGENT_PID=$!

# Start backend-gateway
echo "[2/3] Starting backend-gateway..."
cd ../backend-gateway/cmd/cc-connect
go run . &
GATEWAY_PID=$!

# Start frontend
echo "[3/3] Starting frontend..."
cd ../../../frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "All services started!"
echo "  Backend Agent:  http://localhost:8000"
echo "  Backend Gateway: http://localhost:8080"
echo "  Frontend:       http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $AGENT_PID $GATEWAY_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
