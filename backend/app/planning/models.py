from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    tool: str
    parameters: dict


@dataclass
class ExecutionPlan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
