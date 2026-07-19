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
