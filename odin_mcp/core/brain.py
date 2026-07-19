from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from odin_mcp.models.decision_graph import DecisionGraph


@dataclass(slots=True)
class BrainContext:
    goal: str
    repository_analysis: Any = None
    engineering_plan: Any = None
    execution_result: Any = None
    validation_result: Any = None
    decision_graph: DecisionGraph = field(default_factory=DecisionGraph)


class OdinBrain:
    """
    Central coordinator for Odin.

    The Brain owns the complete engineering lifecycle.
    Individual services remain responsible for their own
    domain logic.
    """

    def __init__(self):
        self._services: dict[str, Any] = {}

    def register(
        self,
        name: str,
        service: Any,
    ) -> None:
        self._services[name] = service

    def service(
        self,
        name: str,
    ) -> Any:
        return self._services[name]

    def create_context(
        self,
        goal: str,
    ) -> BrainContext:

        context = BrainContext(goal=goal)

        context.decision_graph.add_node(
            "goal",
            goal,
            "goal",
        )

        return context
