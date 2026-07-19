from __future__ import annotations

from odin_mcp.models.engineering_plan import EngineeringPlan


class EngineeringPlanner:
    """
    Produces EngineeringPlans from high-level requests.

    Initial implementation is rule-based.
    Future versions will use repository intelligence
    and LLM reasoning.
    """

    def create_replace_plan(
        self,
        *,
        title: str,
        path: str,
        old: str,
        new: str,
        commit_message: str,
        push: bool = False,
    ) -> EngineeringPlan:

        plan = EngineeringPlan(
            title=title,
            description="Automatically generated engineering plan.",
        )

        plan.add_step(
            "replace_text",
            path=path,
            old=old,
            new=new,
            commit_message=commit_message,
            push=push,
        )

        return plan
