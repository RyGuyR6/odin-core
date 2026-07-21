#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${1:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
SERVER="$REPO_ROOT/odin_mcp/server.py"

[[ -f "$SERVER" ]] || {
  echo "Missing $SERVER" >&2
  exit 1
}

cp "$SERVER" "$SERVER.ow005b-render.bak"

python - "$SERVER" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "import os\n" not in text:
    text = text.replace("import platform\n", "import os\nimport platform\n", 1)

starlette_import = (
    "from starlette.requests import Request\n"
    "from starlette.responses import JSONResponse\n"
    "from starlette.routing import Route\n"
)
if "from starlette.requests import Request" not in text:
    anchor = "from mcp.server.fastmcp import FastMCP\n"
    if anchor not in text:
        raise SystemExit("Could not find FastMCP import.")
    text = text.replace(anchor, anchor + "\n" + starlette_import, 1)

text = text.replace(
    '    port=8000,\n',
    '    port=int(os.getenv("PORT", "8000")),\n',
    1,
)

old_tail = 'if __name__ == "__main__":\n    mcp.run(transport="streamable-http")\n'

new_tail = '''async def root(request: Request) -> JSONResponse:
    """Human-readable service landing response."""

    return JSONResponse(
        {
            "name": "Odin MCP",
            "status": "online",
            "transport": "streamable-http",
            "mcp_endpoint": "/mcp",
            "health_endpoint": "/health",
        }
    )


async def health(request: Request) -> JSONResponse:
    """Render health-check endpoint."""

    return JSONResponse(
        {
            "status": "healthy",
            "service": "odin-mcp",
        }
    )


app = mcp.streamable_http_app()
app.router.routes.insert(0, Route("/health", health, methods=["GET"]))
app.router.routes.insert(0, Route("/", root, methods=["GET"]))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
'''

if new_tail not in text:
    if old_tail not in text:
        raise SystemExit("Could not locate the server startup block.")
    text = text.replace(old_tail, new_tail, 1)

path.write_text(text, encoding="utf-8")
PY

python -m compileall "$SERVER"

python - <<'PY'
from odin_mcp.server import app, mcp

paths = [getattr(route, "path", None) for route in app.router.routes]
assert "/" in paths
assert "/health" in paths
assert mcp.settings.streamable_http_path == "/mcp"
print("ASGI app, /health, and /mcp configuration verified.")
PY

cat > "$REPO_ROOT/render-mcp.yaml" <<'YAML'
services:
  - type: web
    name: odin-mcp
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn odin_mcp.server:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    autoDeploy: true
YAML

echo
echo "Render-ready Odin MCP service created."
echo
echo "Local test:"
echo "  python -m odin_mcp.server"
echo
echo "Then in another terminal:"
echo "  curl -s http://localhost:8000/ | python -m json.tool"
echo "  curl -s http://localhost:8000/health | python -m json.tool"
echo
echo "MCP endpoint:"
echo "  http://localhost:8000/mcp"
echo
echo "Render Blueprint example:"
echo "  $REPO_ROOT/render-mcp.yaml"
