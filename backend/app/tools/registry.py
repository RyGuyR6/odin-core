from __future__ import annotations
from threading import RLock
from .base import Tool
from .exceptions import ToolNotFoundError, ToolValidationError

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._lock = RLock()

    def register(self, tool: Tool, replace: bool = False) -> None:
        name = tool.tool_definition().name
        with self._lock:
            if name in self._tools and not replace:
                raise ToolValidationError(f"Tool already registered: {name}")
            self._tools[name] = tool

    def unregister(self, name: str) -> None:
        with self._lock:
            if name not in self._tools:
                raise ToolNotFoundError(name)
            del self._tools[name]

    def get(self, name: str) -> Tool:
        with self._lock:
            tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Unknown tool: {name}")
        return tool

    def list(self) -> list[str]:
        with self._lock:
            return sorted(self._tools)

    def all(self) -> list[Tool]:
        with self._lock:
            return [self._tools[name] for name in sorted(self._tools)]

    def metadata(self) -> list[dict]:
        return [tool.metadata() for tool in self.all()]

registry = ToolRegistry()
