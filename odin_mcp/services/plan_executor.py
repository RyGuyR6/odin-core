from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from odin_mcp.models.engineering_plan import EngineeringPlan
from odin_mcp.services.task_executor import EngineeringTaskExecutor


@dataclass(slots=True)
class StepResult:
    index: int
    action: str
    success: bool
    elapsed: float
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(slots=True)
class PlanResult:
    success: bool
    elapsed: float
    completed_steps: int
    results: list[StepResult] = field(default_factory=list)


class EngineeringPlanExecutor:

    def __init__(
        self,
        executor: EngineeringTaskExecutor,
    ) -> None:
        self.executor = executor

    def execute(
        self,
        plan: EngineeringPlan,
    ) -> PlanResult:

        started = time.perf_counter()

        results: list[StepResult] = []

        for index, step in enumerate(plan.steps):

            step_started = time.perf_counter()

            try:

                output = self.executor.execute(
                    {
                        "action": step.action,
                        **step.parameters,
                    }
                )

                results.append(
                    StepResult(
                        index=index,
                        action=step.action,
                        success=True,
                        elapsed=time.perf_counter() - step_started,
                        result=output,
                    )
                )

            except Exception as exc:

                results.append(
                    StepResult(
                        index=index,
                        action=step.action,
                        success=False,
                        elapsed=time.perf_counter() - step_started,
                        error=str(exc),
                    )
                )

                return PlanResult(
                    success=False,
                    elapsed=time.perf_counter() - started,
                    completed_steps=index,
                    results=results,
                )

        return PlanResult(
            success=True,
            elapsed=time.perf_counter() - started,
            completed_steps=len(results),
            results=results,
        )
