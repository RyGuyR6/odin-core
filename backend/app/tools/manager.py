from __future__ import annotations
from functools import lru_cache
from .builtins import register_builtin_tools
from .config import get_tool_settings
from .executor import ToolExecutor
from .policy import PolicyEngine
from .registry import registry
from .sandbox import WorkspaceSandbox
from .store import ToolStore

class ToolManager:
    def __init__(self):
        self.settings=get_tool_settings()
        self.sandbox=WorkspaceSandbox(self.settings.workspace_root)
        self.store=ToolStore(self.settings.database_path)
        self.policy=PolicyEngine(self.settings)
        register_builtin_tools(registry,self.sandbox,self.settings)
        self.registry=registry
        self.executor=ToolExecutor(self.registry,self.store,self.policy,self.settings)

@lru_cache(maxsize=1)
def get_tool_manager() -> ToolManager:
    return ToolManager()
