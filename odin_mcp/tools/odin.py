from pathlib import Path

from odin_mcp.core.execute import OdinExecuteAPI

api = OdinExecuteAPI(Path("."))

def register_odin_tools(mcp):


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

