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
