from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStatus(str, Enum):
    PLANNED = "planned"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    RETRY_SCHEDULED = "retry_scheduled"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class StepStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


class AttemptStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


TERMINAL_RUN_STATUSES = {
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}
TERMINAL_STEP_STATUSES = {
    StepStatus.SUCCEEDED,
    StepStatus.FAILED,
    StepStatus.CANCELLED,
    StepStatus.SKIPPED,
}


@dataclass(slots=True)
class ExecutionLimits:
    max_attempts: int = 3
    max_steps: int = 100
    max_tool_calls: int = 100
    max_runtime_seconds: int = 3600
    max_cost_usd: float = 10.0

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        if self.max_runtime_seconds < 1:
            raise ValueError("max_runtime_seconds must be positive")
        if self.max_cost_usd < 0:
            raise ValueError("max_cost_usd cannot be negative")


@dataclass(slots=True)
class ExecutionStep:
    id: str
    run_id: str
    position: int
    kind: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    requires_approval: bool = False
    idempotency_key: str | None = None
    status: StepStatus = StepStatus.PENDING
    attempt_count: int = 0
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class ExecutionRun:
    id: str
    goal: str
    status: RunStatus = RunStatus.PLANNED
    repository_id: int | None = None
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    current_step_id: str | None = None
    error: str | None = None
    created_by: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None

    def public(self, *, steps: list[ExecutionStep] | None = None) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        if steps is not None:
            data["steps"] = [step.public() for step in steps]
            completed = sum(step.status in TERMINAL_STEP_STATUSES for step in steps)
            data["progress"] = {
                "completed": completed,
                "total": len(steps),
                "percent": round((completed / len(steps)) * 100, 1) if steps else 100.0,
            }
        return data


@dataclass(slots=True)
class ExecutionAttempt:
    id: str
    run_id: str
    step_id: str
    number: int
    status: AttemptStatus = AttemptStatus.RUNNING
    worker_id: str | None = None
    result: Any = None
    error: str | None = None
    retryable: bool | None = None
    started_at: str = field(default_factory=utc_now)
    completed_at: str | None = None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class ExecutionApproval:
    id: str
    run_id: str
    step_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: str = field(default_factory=utc_now)
    decided_at: str | None = None
    decided_by: str | None = None
    reason: str | None = None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class QueueClaim:
    id: int
    run_id: str
    step_id: str
    worker_id: str
    lease_expires_at: str
