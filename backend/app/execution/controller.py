from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import threading
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
from app.execution.policies import NonRetryableExecutionError, RetryPolicy


class _LeaseHeartbeat:
    def __init__(
        self,
        store: ExecutionStore,
        claim: QueueClaim,
        *,
        lease_seconds: int = 30,
        interval_seconds: float = 10.0,
    ):
        self.store = store
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            if not self.store.heartbeat(self.claim, self.lease_seconds):
                return

    def __exit__(self, *_):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))


class ExecutionController:
    """Executes one leased step at a time and persists every transition."""

    def __init__(
        self,
        store: ExecutionStore,
        *,
        handlers: HandlerRegistry | None = None,
        events: ExecutionEvents | None = None,
        lease_seconds: int = 30,
        heartbeat_seconds: float = 10.0,
    ):
        self.store = store
        self.handlers = handlers or HandlerRegistry()
        self.events = events or ExecutionEvents(store)
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds

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

        resolved_step = replace(
            step, parameters=self._resolve_parameters(run.id, step.parameters)
        )
        try:
            receipt_state, receipt_result = self.store.begin_operation(
                step, claim.worker_id
            )
            if receipt_state == "indeterminate":
                raise NonRetryableExecutionError(
                    "Operation outcome is indeterminate after interruption; "
                    "manual reconciliation is required before retry"
                )
            if receipt_state == "completed":
                result = receipt_result
            else:
                with _LeaseHeartbeat(
                    self.store,
                    claim,
                    lease_seconds=self.lease_seconds,
                    interval_seconds=self.heartbeat_seconds,
                ):
                    result = self.handlers.get(step.kind)(resolved_step, run)
                self.store.complete_operation(step, result)
        except Exception as exc:
            return self._handle_failure(run, step, claim, attempt, exc)

        if not self.store.complete_success(claim, attempt, result):
            return self.store.get_run(run.id)
        self._publish(
            "execution.step.succeeded",
            run.id,
            {"step_id": step.id, "attempt": attempt.number},
        )
        self._advance(run)
        return self.store.get_run(run.id)

    def _resolve_parameters(self, run_id: str, value: Any) -> Any:
        """Resolve {"$ref": "step-id.result.path"} values from dependencies."""
        if isinstance(value, list):
            return [self._resolve_parameters(run_id, item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"$ref"}:
                reference = str(value["$ref"])
                parts = reference.split(".")
                if len(parts) < 2:
                    raise NonRetryableExecutionError(
                        f"Invalid step result reference: {reference}"
                    )
                source = self.store.get_step(run_id, parts[0])
                if source.status != StepStatus.SUCCEEDED:
                    raise NonRetryableExecutionError(
                        f"Referenced step has not succeeded: {parts[0]}"
                    )
                current: Any = source.result
                path = parts[2:] if parts[1] == "result" else parts[1:]
                for part in path:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        raise NonRetryableExecutionError(
                            f"Step result reference not found: {reference}"
                        )
                return current
            return {
                key: self._resolve_parameters(run_id, item)
                for key, item in value.items()
            }
        return value

    def _handle_failure(self, run, step, claim, attempt, exc: Exception):
        retry_policy = RetryPolicy(max_attempts=run.limits.max_attempts)
        retryable = retry_policy.should_retry(exc, attempt.number)
        available = None
        delay = 0.0
        if retryable:
            delay = retry_policy.delay_for(attempt.number)
            available = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat()
        outcome = self.store.complete_failure(
            claim,
            attempt,
            error=str(exc),
            retryable=retryable,
            available_at=available,
        )
        if outcome == "lost":
            return self.store.get_run(run.id)
        if outcome == "retry":
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
