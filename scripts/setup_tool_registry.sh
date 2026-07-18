#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "======================================="
echo " Installing Odin Tool Registry"
echo "======================================="

mkdir -p "$BACKEND/app/registry"

cat > "$BACKEND/app/registry/__init__.py" <<'PY'
from .tool_registry import ToolRegistry, registry

__all__ = [
    "ToolRegistry",
    "registry",
]
PY


cat > "$BACKEND/app/registry/tool_registry.py" <<'PY'
from typing import Dict, Any

from app.sdk.tool import Tool


class ToolRegistry:
    """
    Central registry for all Odin tools.
    """

    def __init__(self):
        self.tools: Dict[str, Tool] = {}


    def register(self, tool: Tool):
        """
        Register a tool.
        """

        self.tools[tool.name] = tool


    def unregister(self, name: str):
        """
        Remove a tool.
        """

        self.tools.pop(name, None)


    def list_tools(self):
        """
        Return available tools.
        """

        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self.tools.values()
        ]


    def get(self, name: str):
        return self.tools.get(name)


    def execute(self, name: str, *args, **kwargs):
        tool = self.get(name)

        if not tool:
            raise ValueError(
                f"Tool '{name}' not found"
            )

        return tool.execute(
            *args,
            **kwargs
        )


registry = ToolRegistry()
PY


echo
echo "Testing registry import..."

cd "$BACKEND"

if [ -d ".venv" ]; then

.venv/bin/python - <<'PY'
from app.registry import registry
from app.sdk import Tool

tool = Tool(
    name="test.tool",
    description="Test tool",
    handler=lambda: "success"
)

registry.register(tool)

assert registry.execute(
    "test.tool"
) == "success"

print("Tool registry working")

PY

fi


echo
echo "======================================="
echo " Odin Tool Registry Installed"
echo "======================================="
