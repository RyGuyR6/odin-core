from dataclasses import dataclass, field


@dataclass
class PlanStep:
    tool: str
    parameters: dict


@dataclass
class ExecutionPlan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
