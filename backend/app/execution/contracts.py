from __future__ import annotations

from typing import Any, Protocol

from app.execution.models import ExecutionRun, ExecutionStep


class StepHandler(Protocol):
    def __call__(
        self,
        step: ExecutionStep,
        run: ExecutionRun,
    ) -> Any: ...


class Planner(Protocol):
    def plan(
        self,
        goal: str,
        *,
        repository_id: int | None,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]: ...


class ExecutionEventPublisher(Protocol):
    def publish(
        self,
        event_type: str,
        *,
        run_id: str,
        payload: dict[str, Any],
    ) -> None: ...
