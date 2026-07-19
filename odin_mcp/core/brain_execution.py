from __future__ import annotations

from odin_mcp.core.brain import BrainContext


class BrainExecutionPipeline:
    """
    Executes an EngineeringPlan and records execution
    in the DecisionGraph.
    """

    def __init__(self, brain):
        self.brain = brain

    def execute(self, context: BrainContext):

        executor = self.brain.service("executor")

        if context.engineering_plan is None:
            raise RuntimeError("No engineering plan has been created.")

        result = executor.execute(context.engineering_plan)

        context.execution_result = result

        context.decision_graph.add_node(
            "execution",
            "Engineering Execution",
            "execution",
            success=result.success,
        )

        context.decision_graph.connect(
            "plan",
            "execution",
            "executed_by",
        )

        if getattr(result, "validation", None) is not None:

            context.validation_result = result.validation

            context.decision_graph.add_node(
                "validation",
                "Validation",
                "validation",
                success=result.validation.success,
            )

            context.decision_graph.connect(
                "execution",
                "validation",
                "validated_by",
            )

        return context
