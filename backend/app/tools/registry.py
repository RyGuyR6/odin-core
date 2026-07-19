from typing import Dict

from .base import Tool


class ToolRegistry:
    """
    Registry for Odin tools.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """
        Register a tool.
        """
        self._tools[tool.name] = tool

    def get(self, name: str):
        """
        Get a tool by name.
        """
        return self._tools.get(name)

    def list(self):
        """
        List all registered tool names.
        """
        return sorted(self._tools.keys())


# Global registry instance used throughout the application
registry = ToolRegistry()