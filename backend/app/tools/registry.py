from typing import Dict

from .base import Tool


class ToolRegistry:
    """
    Registry for Odin tools.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str):
        return self._tools.get(name)

    def list(self):
        """
        Return tool names.
        """
        return sorted(self._tools.keys())

    def all(self):
        """
        Return tool objects.
        """
        return list(self._tools.values())

    def metadata(self):
        """
        Return metadata for every tool.
        """
        return [tool.metadata() for tool in self.all()]


registry = ToolRegistry()
