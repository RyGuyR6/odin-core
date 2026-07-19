from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EngineeringGoal:
    """
    High-level engineering request.
    """

    request: str
    priority: str = "normal"
    validate: bool = True
    commit: bool = True
    push: bool = False


@dataclass(slots=True)
class GoalBreakdown:
    phases: list[str] = field(default_factory=list)

    def add(self, phase: str) -> None:
        self.phases.append(phase)
