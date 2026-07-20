#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/odin-core"
BACKEND="$ROOT/backend"
PYPROJECT="$BACKEND/pyproject.toml"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKEND/pyproject.toml.backup-$STAMP"

if [[ ! -d "$BACKEND" ]]; then
  echo "[FAIL] Backend directory not found: $BACKEND"
  exit 1
fi

if [[ -f "$PYPROJECT" ]]; then
  cp "$PYPROJECT" "$BACKUP"
  echo "[OK] Backup created: $BACKUP"
fi

cat > "$PYPROJECT" <<'TOML'
[project]
name = "odin-core"
version = "0.1.0"
description = "Odin AI Software Engineering Platform"
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.139.2",
    "uvicorn>=0.51.0",
    "pydantic>=2.13.4",
    "pydantic-settings>=2.14.2",
    "python-dotenv>=1.2.2",
    "python-multipart>=0.0.32",

    "pwdlib[argon2]>=0.3.0",
    "PyJWT>=2.10.1",
    "cryptography>=49.0.0",

    "mcp[cli]>=1.28.1",
    "sse-starlette>=3.4.5",

    "psutil>=7.2.2",

    "GitPython>=3.1.46",
    "requests>=2.32.5",
    "httpx>=0.28.1",
    "httpx2>=2.7.0",

    "pytest>=9.1.1",
    "pytest-mock>=3.15.1",
]

[tool.black]
line-length = 88
target-version = ["py312"]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
TOML

echo "[OK] Rewrote backend/pyproject.toml"

cd "$BACKEND"

echo "[INFO] Synchronizing Python environment..."
UV_LINK_MODE=copy uv sync

echo "[INFO] Verifying required imports..."
uv run python - <<'PY'
from mcp.server.fastmcp import FastMCP
import fastapi
import psutil
import jwt
import multipart
import sse_starlette
import git

print("FastAPI:", fastapi.__version__)
print("MCP: OK")
print("psutil:", psutil.__version__)
print("PyJWT:", jwt.__version__)
print("python-multipart: OK")
print("sse-starlette: OK")
print("GitPython: OK")
PY

echo "[INFO] Compiling backend..."
uv run python -m compileall -q app

echo
echo "[OK] backend/pyproject.toml repaired successfully."
echo "[OK] MCP and psutil will now survive future uv sync runs."
