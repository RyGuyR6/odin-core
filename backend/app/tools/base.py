from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from .models import ExecutionContext, RiskLevel, ToolDefinition

class Tool(ABC):
    """
    Unified Odin tool base.

    It preserves the original synchronous BaseTool contract used by the MCP
    loader while also supporting Milestone 20 tools that declare a
    ToolDefinition and implement async execution.
    """
    definition: ToolDefinition | None = None
    category: str = "general"
    tags: list[str] = []

    @property
    def name(self) -> str:
        definition = getattr(type(self), "definition", None)
        return definition.name if isinstance(definition, ToolDefinition) else ""

    @property
    def description(self) -> str:
        definition = getattr(type(self), "definition", None)
        return definition.description if isinstance(definition, ToolDefinition) else ""

    @property
    def version(self) -> str:
        definition = getattr(type(self), "definition", None)
        return definition.version if isinstance(definition, ToolDefinition) else "1.0.0"

    def tool_definition(self) -> ToolDefinition:
        definition = getattr(type(self), "definition", None)
        if isinstance(definition, ToolDefinition):
            return definition
        return ToolDefinition(
            name=str(getattr(self, "name", "")),
            description=str(getattr(self, "description", "")),
            version=str(getattr(self, "version", "1.0.0")),
            risk=RiskLevel.low,
            requires_approval=False,
            tags=list(getattr(self, "tags", [])),
        )

    def metadata(self) -> dict[str, Any]:
        data = self.tool_definition().model_dump(mode="json")
        data["category"] = getattr(self, "category", "general")
        return data

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        Legacy tools implement synchronous execute(**kwargs).
        Milestone 20 tools implement async execute(arguments, context).
        """
        raise NotImplementedError

# Backwards-compatible import used by existing *_tool modules.
BaseTool = Tool
