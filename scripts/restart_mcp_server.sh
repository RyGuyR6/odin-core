#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "Stopping anything using port 8000..."

PIDS=$(lsof -ti:8000 || true)

if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill -9
    sleep 1
fi

echo
echo "Starting Odin MCP..."

export ODIN_GIT_WRITE_ENABLED=true
export ODIN_REPO_WRITE_ENABLED=true

exec python -m odin_mcp.server
