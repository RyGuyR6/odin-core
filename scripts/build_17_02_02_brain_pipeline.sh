#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cat > odin_mcp/core/brain_pipeline.py <<'PY'
from __future__ import annotations

from odin_mcp.core.brain import BrainContext


class BrainPipeline:
    """
    Executes the high-level Odin engineering pipeline.

    Repository Analysis
        ↓
    Engineering Planning
        ↓
    Execution
        ↓
    Validation
    """

    def __init__(self, brain):
        self.brain = brain

    def run(self, context: BrainContext):

        repo_planner = self.brain.service("repository_planner")
        eng_planner = self.brain.service("engineering_planner")
        executor = self.brain.service("executor")

        #
        # Repository Analysis
        #

        analysis = repo_planner.analyze(context.goal)

        context.repository_analysis = analysis

        context.decision_graph.add_node(
            "analysis",
            "Repository Analysis",
            "analysis",
        )

        context.decision_graph.connect(
            "goal",
            "analysis",
            "analyzed_by",
        )

        #
        # Engineering Plan
        #

        plan = eng_planner.create_replace_plan(
            title=context.goal,
            path="",
            old="",
            new="",
            commit_message=context.goal,
        )

        context.engineering_plan = plan

        context.decision_graph.add_node(
            "plan",
            plan.title,
            "plan",
        )

        context.decision_graph.connect(
            "analysis",
            "plan",
            "generated",
        )

        #
        # Execution intentionally disabled.
        #
        # The Brain currently plans only.
        #
        # Future:
        #
        # context.execution_result =
        #     executor.execute(...)
        #

        return context
PY

cat > scripts/test_brain_pipeline.py <<'PY'
from pathlib import Path

from odin_mcp.core.brain import OdinBrain
from odin_mcp.core.brain_pipeline import BrainPipeline

from odin_mcp.services.repository_planner import RepositoryPlanner
from odin_mcp.services.repository_search_service import RepositorySearchService
from odin_mcp.services.engineering_planner import EngineeringPlanner

brain = OdinBrain()

repo = RepositorySearchService(Path("."))

brain.register(
    "repository_planner",
    RepositoryPlanner(repo),
)

brain.register(
    "engineering_planner",
    EngineeringPlanner(),
)

brain.register(
    "executor",
    None,
)

pipeline = BrainPipeline(brain)

ctx = brain.create_context(
    "Add JWT authentication"
)

ctx = pipeline.run(ctx)

print()

print("Goal")
print("-----")
print(ctx.goal)

print()

print("Decision Graph")
print("--------------")
print(ctx.decision_graph)

print()

print("Repository Analysis")
print("-------------------")
print(ctx.repository_analysis)

print()

print("Engineering Plan")
print("----------------")
print(ctx.engineering_plan)
PY

python -m compileall -q \
    odin_mcp/core/brain_pipeline.py \
    scripts/test_brain_pipeline.py

echo
echo "======================================="
echo " Brain Pipeline Installed"
echo "======================================="
echo
echo "Run:"
echo
echo "python scripts/test_brain_pipeline.py"
echo
