import importlib
import inspect
import pkgutil

import app.tools as tools_package
from app.tools.base import Tool
from app.tools.registry import registry


_loaded = False


def load_tools() -> None:
    """
    Discover and register Tool subclasses from app.tools modules.

    Only modules ending in "_tool" are scanned. Loading is idempotent,
    so it is safe for both Odin and the MCP server to call this function.
    """
    global _loaded

    if _loaded:
        return

    for module_info in pkgutil.iter_modules(tools_package.__path__):
        module_name = module_info.name

        if not module_name.endswith("_tool"):
            continue

        module = importlib.import_module(f"app.tools.{module_name}")

        for _, tool_class in inspect.getmembers(module, inspect.isclass):
            if tool_class is Tool:
                continue

            if not issubclass(tool_class, Tool):
                continue

            # Avoid registering classes merely imported into the module.
            if tool_class.__module__ != module.__name__:
                continue

            tool = tool_class()

            if not tool.name:
                raise ValueError(
                    f"{tool_class.__name__} must define a non-empty name"
                )

            registry.register(tool)

    _loaded = True
