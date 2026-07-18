#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "======================================="
echo " Installing Odin SDK"
echo " Root: $ROOT"
echo "======================================="

if [ ! -d "$BACKEND/app" ]; then
    echo "ERROR: backend/app not found"
    exit 1
fi

mkdir -p "$BACKEND/app/sdk"

echo "Creating SDK files..."

cat > "$BACKEND/app/sdk/__init__.py" <<'PY'
from .plugin import Plugin
from .tool import Tool
from .context import Context

__all__ = [
    "Plugin",
    "Tool",
    "Context",
]
PY


cat > "$BACKEND/app/sdk/context.py" <<'PY'
class Context:
    """
    Runtime context passed into plugins and tools.
    """

    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)
PY


cat > "$BACKEND/app/sdk/tool.py" <<'PY'
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable

    def execute(self, *args, **kwargs):
        return self.handler(*args, **kwargs)
PY


cat > "$BACKEND/app/sdk/plugin.py" <<'PY'
from abc import ABC, abstractmethod


class Plugin(ABC):

    name = "unknown"
    version = "0.1.0"

    def load(self, context):
        pass

    def unload(self):
        pass

    def tools(self):
        return []
PY


echo
echo "Testing import..."

cd "$BACKEND"

if [ -d ".venv" ]; then
    .venv/bin/python - <<'PY'
from app.sdk import Plugin, Tool, Context

print("SDK import successful")
PY
else
    echo "WARNING: .venv missing, skipping import test"
fi

echo
echo "======================================="
echo " Odin SDK installed successfully"
echo "======================================="
