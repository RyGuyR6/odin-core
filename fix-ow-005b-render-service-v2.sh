#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="${1:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
SERVER="$REPO_ROOT/odin_mcp/server.py"

[[ -f "$SERVER" ]] || {
  echo "Missing $SERVER" >&2
  exit 1
}

cp "$SERVER" "$SERVER.ow005b-render-v2.bak"

python - "$SERVER" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if not re.search(r"^import os$", text, re.MULTILINE):
    match = re.search(r"^(import [^\n]+\n)", text, re.MULTILINE)
    if match:
        text = text[:match.start()] + "import os\n" + text[match.start():]
    else:
        text = "import os\n" + text

if "from starlette.requests import Request" not in text:
    anchor = "from mcp.server.fastmcp import FastMCP\n"
    imports = (
        "\nfrom starlette.requests import Request\n"
        "from starlette.responses import JSONResponse\n"
        "from starlette.routing import Route\n"
    )
    if anchor not in text:
        raise SystemExit("Could not find FastMCP import.")
    text = text.replace(anchor, anchor + imports, 1)

text = re.sub(
    r"(\bport\s*=\s*)8000(\s*,)",
    r'\1int(os.getenv("PORT", "8000"))\2',
    text,
    count=1,
)

main_match = re.search(
    r'\nif __name__\s*==\s*["\']__main__["\']\s*:\s*\n[\s\S]*\Z',
    text,
)
if main_match:
    text = text[:main_match.start()].rstrip() + "\n"

marker = "\nasync def root(request: Request) -> JSONResponse:"
marker_index = text.find(marker)
if marker_index != -1:
    text = text[:marker_index].rstrip() + "\n"

addition = '''

async def root(request: Request) -> JSONResponse:
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

text = text.rstrip() + addition
path.write_text(text, encoding="utf-8")
PY

python -m compileall "$SERVER"

python - <<'PY'
from odin_mcp.server import app, mcp

paths = [getattr(route, "path", None) for route in app.router.routes]
assert "/" in paths, paths
assert "/health" in paths, paths
assert mcp.settings.streamable_http_path == "/mcp"
print("Verified: /, /health, and /mcp")
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
echo "Render-ready MCP service applied."
echo "Start it with:"
echo "  python -m odin_mcp.server"
echo
echo "Test in a second terminal:"
echo "  curl -s http://localhost:8000/ | python -m json.tool"
echo "  curl -s http://localhost:8000/health | python -m json.tool"
