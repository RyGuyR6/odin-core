#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

path = Path("odin_mcp/tools/odin.py")

if path.exists():
    text = path.read_text()
else:
    text = """from pathlib import Path

from odin_mcp.core.execute import OdinExecuteAPI

api = OdinExecuteAPI(Path("."))

def register(mcp):
"""
    
if 'name="odin.execute"' in text:
    print("odin.execute already registered.")
    raise SystemExit

addition = '''

    @mcp.tool(name="odin.execute")
    def odin_execute(
        goal: str,
    ):
        """
        Execute a high-level engineering goal.

        This is the primary public interface for Odin.
        """

        result = api.execute(goal)

        return {
            "success": result.success,
            "goal": result.goal,
            "context": result.context,
        }

'''

text += addition
path.write_text(text)

print("odin_mcp/tools/odin.py updated")
PY

python -m compileall -q odin_mcp/tools/odin.py

echo
echo "✓ odin.execute tool created."
echo
echo "NOTE:"
echo "Register odin.register(mcp) from your server startup if it is not already wired in."
