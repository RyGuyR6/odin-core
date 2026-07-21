"""
Builds execution context for AI tasks.
"""

from dataclasses import dataclass, field
from typing import Any

from app.services.repository_intelligence import repository_intelligence_service


@dataclass
class ExecutionContext:
    objective: str
    repository: str | None = None
    files: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    """
    Collects everything the AI needs before planning a task.
    """

    def build(
        self,
        objective: str,
        repository: str | None = None,
    ) -> ExecutionContext:
        metadata: dict[str, Any] = {}
        if repository:
            repository_context = repository_intelligence_service.render_repository_context(
                repository
            )
            if repository_context:
                metadata["repository_context"] = repository_context
        return ExecutionContext(
            objective=objective,
            repository=repository,
            metadata=metadata,
        )
