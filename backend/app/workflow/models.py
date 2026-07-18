from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowTask:
    id: str
    objective: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    success: bool
    message: str
    artifacts: list[Any] = field(default_factory=list)
