from time import perf_counter

from app.tools.registry import registry


class ExecutionEngine:
    """
    Executes Odin tools through a single entry point.
    """

    def execute(self, tool_name: str, **kwargs):
        tool = registry.get(tool_name)

        start = perf_counter()

        result = tool.execute(**kwargs)

        elapsed = round((perf_counter() - start) * 1000, 2)

        return {
            "tool": tool.name,
            "version": tool.version,
            "success": True,
            "elapsed_ms": elapsed,
            "result": result,
        }


executor = ExecutionEngine()
