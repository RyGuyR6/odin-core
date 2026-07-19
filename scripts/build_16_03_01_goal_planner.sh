#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p odin_mcp/models
mkdir -p odin_mcp/services

cat > odin_mcp/models/engineering_goal.py <<'PY'
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
PY

cat > odin_mcp/services/goal_planner.py <<'PY'
from __future__ import annotations

from odin_mcp.models.engineering_goal import (
    EngineeringGoal,
    GoalBreakdown,
)


class GoalPlanner:
    """
    Converts high-level engineering requests into
    execution phases.

    Future versions will incorporate repository
    intelligence and LLM reasoning.
    """

    def create_breakdown(
        self,
        goal: EngineeringGoal,
    ) -> GoalBreakdown:

        breakdown = GoalBreakdown()

        breakdown.add("analyze_repository")
        breakdown.add("identify_targets")
        breakdown.add("generate_plan")
        breakdown.add("execute_plan")

        if goal.validate:
            breakdown.add("validate")

        if goal.commit:
            breakdown.add("commit")

        if goal.push:
            breakdown.add("push")

        return breakdown
PY

cat > scripts/test_goal_planner.py <<'PY'
from odin_mcp.models.engineering_goal import EngineeringGoal
from odin_mcp.services.goal_planner import GoalPlanner

planner = GoalPlanner()

goal = EngineeringGoal(
    request="Add JWT authentication",
    validate=True,
    commit=True,
    push=False,
)

breakdown = planner.create_breakdown(goal)

print("Goal:")
print(goal)
print()
print("Execution Phases:")

for i, phase in enumerate(breakdown.phases, start=1):
    print(f"{i}. {phase}")
PY

python -m compileall -q \
    odin_mcp/models/engineering_goal.py \
    odin_mcp/services/goal_planner.py \
    scripts/test_goal_planner.py

echo
echo "✓ Goal planner foundation created."
echo
echo "Run:"
echo "python scripts/test_goal_planner.py"
