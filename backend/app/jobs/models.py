"""Job models for background Odin operations."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


TERMINAL_JOB_STATUSES = {
    "completed",
    "failed",
    "cancelled",
}


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    """A unit of background work executed by Odin."""

    tool: str
    payload: dict[str, Any]

    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "queued"

    progress: int = 0
    message: str | None = None

    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str = field(default_factory=utc_now)

    result: Any = None
    error: str | None = None

    context_id: str | None = None

    def touch(self) -> None:
        self.updated_at = utc_now()

    def start(self) -> None:
        if self.status != "queued":
            raise ValueError(
                f"Cannot start job in status: {self.status}"
            )

        self.status = "running"
        self.started_at = utc_now()
        self.progress = max(self.progress, 1)
        self.message = "Job started."
        self.touch()

    def update_progress(
        self,
        progress: int,
        message: str | None = None,
    ) -> None:
        if self.status in TERMINAL_JOB_STATUSES:
            raise ValueError("Cannot update a completed job.")

        if progress < 0 or progress > 100:
            raise ValueError("Job progress must be between 0 and 100.")

        self.progress = progress

        if message is not None:
            self.message = message

        self.touch()

    def complete(self, result: Any) -> None:
        self.status = "completed"
        self.progress = 100
        self.result = result
        self.error = None
        self.message = "Job completed."
        self.completed_at = utc_now()
        self.touch()

    def fail(self, error: str | Exception) -> None:
        self.status = "failed"
        self.error = str(error)
        self.message = "Job failed."
        self.completed_at = utc_now()
        self.touch()

    def cancel(self) -> None:
        if self.status in TERMINAL_JOB_STATUSES:
            return

        self.status = "cancelled"
        self.message = "Job cancelled."
        self.completed_at = utc_now()
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
