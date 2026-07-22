"""Execution-plan runner with context and event tracking."""

from app.context.service import context_service
from app.core.executor import executor
from app.events.bus import event_bus


class PlanExecutor:
    """Executes a plan while recording context and event history."""

    def execute(
        self,
        plan,
        context_id: str | None = None,
    ):
        if context_id:
            context = context_service.get(context_id)
        else:
            context = context_service.create(
                goal=plan.goal,
                variables=dict(getattr(plan, "metadata", {}) or {}),
            )

        context.set_status("running")

        event_bus.publish(
            "plan.started",
            source="plan_executor",
            correlation_id=context.id,
            payload={
                "context_id": context.id,
                "goal": plan.goal,
                "step_count": len(plan.steps),
            },
        )

        try:
            for index, step in enumerate(
                plan.steps,
                start=context.current_step,
            ):
                event_bus.publish(
                    "plan.step.started",
                    source="plan_executor",
                    correlation_id=context.id,
                    payload={
                        "context_id": context.id,
                        "step": index,
                        "tool": step.tool,
                        "parameters": step.parameters,
                    },
                )

                result = executor.execute(
                    step.tool,
                    **step.parameters,
                )

                context.add_result(
                    step=index,
                    tool=step.tool,
                    result=result,
                )

                event_bus.publish(
                    "plan.step.completed",
                    source="plan_executor",
                    correlation_id=context.id,
                    payload={
                        "context_id": context.id,
                        "step": index,
                        "tool": step.tool,
                        "result": result,
                    },
                )

            context.set_status("completed")

            event_bus.publish(
                "plan.completed",
                source="plan_executor",
                correlation_id=context.id,
                payload=context.to_dict(),
            )

        except Exception as exc:
            context.set_error(exc)

            event_bus.publish(
                "plan.failed",
                source="plan_executor",
                correlation_id=context.id,
                payload={
                    "context_id": context.id,
                    "goal": plan.goal,
                    "error": str(exc),
                },
            )

            raise

        return context


plan_executor = PlanExecutor()
