from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.execution.events import ExecutionEvents
from app.execution.handlers import HandlerRegistry
from app.execution.models import (
    ApprovalStatus,
    AttemptStatus,
    ExecutionRun,
    QueueClaim,
    RunStatus,
    StepStatus,
    TERMINAL_STEP_STATUSES,
    utc_now,
)
from app.execution.persistence import ExecutionStore
from app.execution.policies import RetryPolicy


class ExecutionController:
    """Executes one leased step at a time and persists every transition."""

    def __init__(
        self,
        store: ExecutionStore,
        *,
        handlers: HandlerRegistry | None = None,
        events: ExecutionEvents | None = None,
    ):
        self.store = store
        self.handlers = handlers or HandlerRegistry()
        self.events = events or ExecutionEvents(store)

    def _publish(
        self, event_type: str, run_id: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.events.publish(event_type, run_id=run_id, payload=payload)

    def process_claim(self, claim: QueueClaim) -> ExecutionRun:
        run = self.store.get_run(claim.run_id)
        step = self.store.get_step(claim.run_id, claim.step_id)
        if run.status == RunStatus.CANCELLED:
            self.store.release_claim(claim)
            return run

        dependencies = {item.id: item for item in self.store.list_steps(run.id)}
        if any(
            dependencies.get(dep) is None
            or dependencies[dep].status != StepStatus.SUCCEEDED
            for dep in step.depends_on
        ):
            self.store.release_claim(claim, delete=False)
            return run

        approval = self.store.approval_for_step(run.id, step.id)
        if step.requires_approval and approval != ApprovalStatus.APPROVED:
            if approval == ApprovalStatus.REJECTED:
                return self._fail_rejected(run, step, claim)
            self.store.request_approval(run.id, step.id)
            step.status = StepStatus.AWAITING_APPROVAL
            run.status = RunStatus.AWAITING_APPROVAL
            run.current_step_id = step.id
            self.store.update_step(step)
            self.store.update_run(run)
            self.store.release_claim(claim)
            self._publish(
                "execution.approval.required", run.id, {"step_id": step.id}
            )
            return run

        run.status = RunStatus.RUNNING
        run.started_at = run.started_at or utc_now()
        run.current_step_id = step.id
        step.status = StepStatus.RUNNING
        step.started_at = step.started_at or utc_now()
        step.error = None
        self.store.update_run(run)
        self.store.update_step(step)
        attempt = self.store.begin_attempt(step, claim.worker_id)
        step.attempt_count = attempt.number
        self.store.update_step(step)
        self._publish(
            "execution.step.started",
            run.id,
            {"step_id": step.id, "attempt": attempt.number},
        )

        try:
            result = self.handlers.get(step.kind)(step, run)
        except Exception as exc:
            return self._handle_failure(run, step, claim, attempt, exc)

        attempt.status = AttemptStatus.SUCCEEDED
        attempt.result = result
        attempt.completed_at = utc_now()
        step.status = StepStatus.SUCCEEDED
        step.result = result
        step.completed_at = attempt.completed_at
        self.store.finish_attempt(attempt)
        self.store.update_step(step)
        self.store.release_claim(claim)
        self._publish(
            "execution.step.succeeded",
            run.id,
            {"step_id": step.id, "attempt": attempt.number},
        )
        self._advance(run)
        return self.store.get_run(run.id)

    def _handle_failure(self, run, step, claim, attempt, exc: Exception):
        retry_policy = RetryPolicy(max_attempts=run.limits.max_attempts)
        retryable = retry_policy.should_retry(exc, attempt.number)
        attempt.status = AttemptStatus.FAILED
        attempt.error = str(exc)
        attempt.retryable = retryable
        attempt.completed_at = utc_now()
        self.store.finish_attempt(attempt)
        step.error = str(exc)

        if retryable:
            delay = retry_policy.delay_for(attempt.number)
            available = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat()
            step.status = StepStatus.RETRY_SCHEDULED
            run.status = RunStatus.RETRY_SCHEDULED
            self.store.update_step(step)
            self.store.update_run(run)
            self.store.release_claim(claim)
            self.store.enqueue(run.id, step.id, available_at=available)
            self._publish(
                "execution.step.retry_scheduled",
                run.id,
                {
                    "step_id": step.id,
                    "attempt": attempt.number,
                    "delay_seconds": delay,
                    "error": str(exc),
                },
            )
        else:
            step.status = StepStatus.FAILED
            step.completed_at = utc_now()
            run.status = RunStatus.FAILED
            run.error = str(exc)
            run.completed_at = step.completed_at
            self.store.update_step(step)
            self.store.update_run(run)
            self.store.release_claim(claim)
            self._publish(
                "execution.failed",
                run.id,
                {"step_id": step.id, "error": str(exc)},
            )
        return self.store.get_run(run.id)

    def _fail_rejected(self, run, step, claim):
        now = utc_now()
        step.status = StepStatus.CANCELLED
        step.error = "Human approval rejected"
        step.completed_at = now
        run.status = RunStatus.CANCELLED
        run.error = step.error
        run.completed_at = now
        run.cancelled_at = now
        self.store.update_step(step)
        self.store.update_run(run)
        self.store.release_claim(claim)
        self._publish(
            "execution.approval.rejected", run.id, {"step_id": step.id}
        )
        return run

    def _advance(self, run: ExecutionRun) -> None:
        steps = self.store.list_steps(run.id)
        if all(step.status in TERMINAL_STEP_STATUSES for step in steps):
            run.status = (
                RunStatus.SUCCEEDED
                if all(
                    step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
                    for step in steps
                )
                else RunStatus.FAILED
            )
            run.current_step_id = None
            run.completed_at = utc_now()
            self.store.update_run(run)
            self._publish(f"execution.{run.status.value}", run.id)
            return

        completed = {step.id for step in steps if step.status == StepStatus.SUCCEEDED}
        queued = False
        for step in steps:
            if step.status in {
                StepStatus.PENDING,
                StepStatus.INTERRUPTED,
                StepStatus.AWAITING_APPROVAL,
            } and all(dep in completed for dep in step.depends_on):
                step.status = StepStatus.QUEUED
                self.store.update_step(step)
                self.store.enqueue(run.id, step.id)
                queued = True
        if queued:
            run.status = RunStatus.QUEUED
            self.store.update_run(run)

    def recover(self) -> list[tuple[str, str]]:
        recovered = self.store.recover_expired()
        for run_id, step_id in recovered:
            step = self.store.get_step(run_id, step_id)
            step.status = StepStatus.QUEUED
            self.store.update_step(step)
            run = self.store.get_run(run_id)
            run.status = RunStatus.QUEUED
            self.store.update_run(run)
            self._publish(
                "execution.recovered", run_id, {"step_id": step_id}
            )
        return recovered
