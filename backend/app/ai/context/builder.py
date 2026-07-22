"""
Builds execution context for AI tasks.
"""

from dataclasses import dataclass, field
from typing import Any

from app.services.repository_context import repository_context_service


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
            package = repository_context_service.get_context(repository, objective)
            metadata["repository_context"] = repository_context_service.render(package)
        return ExecutionContext(
            objective=objective,
            repository=repository,
            metadata=metadata,
        )
