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
