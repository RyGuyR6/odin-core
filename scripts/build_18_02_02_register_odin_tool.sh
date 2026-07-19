#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

tool = Path("odin_mcp/tools/odin.py")
text = tool.read_text()

# Rename the registration function if needed.
if "def register(" in text and "def register_odin_tools(" not in text:
    text = text.replace(
        "def register(mcp):",
        "def register_odin_tools(mcp):",
    )
    tool.write_text(text)
    print("✓ Updated odin.py registration function")

server = Path("odin_mcp/server.py")
server_text = server.read_text()

# Add import.
import_line = "from odin_mcp.tools.odin import register_odin_tools"
if import_line not in server_text:
    lines = server_text.splitlines()

    insert_after = None
    for i, line in enumerate(lines):
        if line.startswith("from odin_mcp.tools."):
            insert_after = i

    if insert_after is None:
        raise SystemExit("Couldn't locate tool imports.")

    lines.insert(insert_after + 1, import_line)
    server_text = "\n".join(lines)

# Add registration.
if "register_odin_tools(mcp)" not in server_text:
    marker = "register_engineering_tools(mcp)"

    if marker not in server_text:
        raise SystemExit("Couldn't locate engineering registration.")

    server_text = server_text.replace(
        marker,
        marker + "\nregister_odin_tools(mcp)",
    )

server.write_text(server_text)

print("✓ Updated server.py")
PY

python -m compileall -q odin_mcp

echo
echo "Restart the server:"
echo "./scripts/restart_mcp_server.sh"
echo
echo "Then verify odin.execute appears in your MCP tool list."
