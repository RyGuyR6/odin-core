#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p odin_mcp/services

cat > odin_mcp/services/engineering_planner.py <<'PY'
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
PY

cat > scripts/test_engineering_planner.py <<'PY'
from odin_mcp.services.engineering_planner import EngineeringPlanner

planner = EngineeringPlanner()

plan = planner.create_replace_plan(
    title="Replace demo",
    path="odin_mcp_write_test.txt",
    old="old",
    new="new",
    commit_message="planner test",
)

print(plan)
print(f"Steps: {plan.step_count}")
for i, step in enumerate(plan.steps, start=1):
    print(f"{i}. {step.action} -> {step.parameters}")
PY

python -m compileall -q \
    odin_mcp/services/engineering_planner.py \
    scripts/test_engineering_planner.py

echo
echo "✓ EngineeringPlanner created."
echo "Run:"
echo "python scripts/test_engineering_planner.py"
