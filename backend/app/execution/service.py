from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.execution.controller import ExecutionController
from app.execution.events import ExecutionEvents
from app.execution.handlers import HandlerRegistry
from app.execution.models import (
    ExecutionLimits,
    ExecutionRun,
    ExecutionStep,
    RunStatus,
    StepStatus,
    TERMINAL_RUN_STATUSES,
    utc_now,
)
from app.execution.persistence import ExecutionStore, ExecutionStoreError


class ExecutionService:
    def __init__(
        self,
        store: ExecutionStore | None = None,
        *,
        handlers: HandlerRegistry | None = None,
    ):
        self.store = store or ExecutionStore()
        self.events = ExecutionEvents(self.store)
        self.controller = ExecutionController(
            self.store, handlers=handlers, events=self.events
        )

    def create(
        self,
        *,
        goal: str,
        steps: list[dict[str, Any]],
        repository_id: int | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        limits: ExecutionLimits | None = None,
        created_by: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise ValueError("Execution goal is required")
        if not steps:
            raise ValueError("An execution plan requires at least one step")
        resolved_limits = limits or ExecutionLimits()
        resolved_limits.validate()
        if len(steps) > resolved_limits.max_steps:
            raise ValueError("Execution plan exceeds max_steps")

        run = ExecutionRun(
            id=run_id or uuid.uuid4().hex,
            goal=goal,
            repository_id=repository_id,
            context=dict(context or {}),
            metadata=dict(metadata or {}),
            limits=resolved_limits,
            created_by=created_by,
        )
        normalized: list[ExecutionStep] = []
        ids: set[str] = set()
        for position, raw in enumerate(steps):
            step_id = str(raw.get("id") or f"step-{position + 1}")
            if step_id in ids:
                raise ValueError(f"Duplicate execution step id: {step_id}")
            ids.add(step_id)
            kind = str(raw.get("kind") or raw.get("action") or "").strip()
            if not kind:
                raise ValueError(f"Execution step {step_id} requires a kind")
            normalized.append(
                ExecutionStep(
                    id=step_id,
                    run_id=run.id,
                    position=position,
                    kind=kind,
                    parameters=dict(raw.get("parameters") or {}),
                    depends_on=list(raw.get("depends_on") or []),
                    requires_approval=bool(raw.get("requires_approval", False)),
                    idempotency_key=raw.get("idempotency_key"),
                )
            )
        for step in normalized:
            unknown = set(step.depends_on) - ids
            if unknown:
                raise ValueError(
                    f"Step {step.id} has unknown dependencies: {sorted(unknown)}"
                )
            if step.id in step.depends_on:
                raise ValueError(f"Step {step.id} cannot depend on itself")
        dependency_map = {step.id: set(step.depends_on) for step in normalized}
        resolved: set[str] = set()
        while remaining := set(dependency_map) - resolved:
            ready = {
                step_id
                for step_id in remaining
                if dependency_map[step_id] <= resolved
            }
            if not ready:
                raise ValueError("Execution plan contains a dependency cycle")
            resolved.update(ready)

        self.store.create_run(run, normalized)
        self.events.publish(
            "execution.planned",
            run_id=run.id,
            payload={"goal": goal, "step_count": len(normalized)},
        )
        self.resume(run.id)
        return self.get(run.id)

    def get(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        payload = run.public(steps=self.store.list_steps(run_id))
        payload["pending_approval"] = (
            approval.public()
            if (approval := self.store.pending_approval(run_id))
            else None
        )
        return payload

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            run.public(steps=self.store.list_steps(run.id))
            for run in self.store.list_runs(limit)
        ]

    def resume(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            raise ExecutionStoreError(
                f"Cannot resume execution in state {run.status.value}"
            )
        if self.store.pending_approval(run_id):
            return self.get(run_id)
        steps = self.store.list_steps(run_id)
        completed = {step.id for step in steps if step.status == StepStatus.SUCCEEDED}
        queued = 0
        for step in steps:
            if step.status in {
                StepStatus.PENDING,
                StepStatus.INTERRUPTED,
                StepStatus.AWAITING_APPROVAL,
                StepStatus.RETRY_SCHEDULED,
            } and all(dep in completed for dep in step.depends_on):
                step.status = StepStatus.QUEUED
                self.store.update_step(step)
                self.store.enqueue(run_id, step.id)
                queued += 1
        if queued:
            run.status = RunStatus.QUEUED
            run.error = None
            self.store.update_run(run)
            self.events.publish(
                "execution.queued",
                run_id=run_id,
                payload={"step_count": queued},
            )
        return self.get(run_id)

    def approve(
        self, run_id: str, *, actor: str, reason: str | None = None
    ) -> dict[str, Any]:
        approval = self.store.decide_approval(
            run_id, approved=True, actor=actor, reason=reason
        )
        self.events.publish(
            "execution.approval.approved",
            run_id=run_id,
            payload={"step_id": approval.step_id, "actor": actor},
        )
        return self.resume(run_id)

    def reject(
        self, run_id: str, *, actor: str, reason: str | None = None
    ) -> dict[str, Any]:
        approval = self.store.decide_approval(
            run_id, approved=False, actor=actor, reason=reason
        )
        run = self.store.get_run(run_id)
        step = self.store.get_step(run_id, approval.step_id)
        now = utc_now()
        step.status = StepStatus.CANCELLED
        step.error = reason or "Human approval rejected"
        step.completed_at = now
        run.status = RunStatus.CANCELLED
        run.error = step.error
        run.cancelled_at = now
        run.completed_at = now
        self.store.update_step(step)
        self.store.update_run(run)
        self.events.publish(
            "execution.approval.rejected",
            run_id=run_id,
            payload={"step_id": step.id, "actor": actor, "reason": reason},
        )
        return self.get(run_id)

    def cancel(self, run_id: str, *, actor: str | None = None) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            return self.get(run_id)
        now = utc_now()
        run.status = RunStatus.CANCELLED
        run.cancelled_at = now
        run.completed_at = now
        for step in self.store.list_steps(run_id):
            if step.status not in {
                StepStatus.SUCCEEDED,
                StepStatus.FAILED,
                StepStatus.SKIPPED,
            }:
                step.status = StepStatus.CANCELLED
                step.completed_at = now
                self.store.update_step(step)
        self.store.update_run(run)
        self.events.publish(
            "execution.cancelled", run_id=run_id, payload={"actor": actor}
        )
        return self.get(run_id)

    def run_next(self, worker_id: str = "api-worker") -> dict[str, Any] | None:
        claim = self.store.claim_next(worker_id)
        if claim is None:
            return None
        run = self.controller.process_claim(claim)
        return self.get(run.id)

    def events_for(self, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
        self.store.get_run(run_id)
        return self.store.list_events(run_id, limit)

    def attempts_for(self, run_id: str) -> list[dict[str, Any]]:
        self.store.get_run(run_id)
        return self.store.list_attempts(run_id)


execution_service = ExecutionService(
    ExecutionStore(Path(".odin") / "executions.db")
)
