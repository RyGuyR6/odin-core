from __future__ import annotations

from dataclasses import dataclass


class NonRetryableExecutionError(RuntimeError):
    """A step failure that must not be retried."""


class ApprovalRequired(RuntimeError):
    """Raised when a step must pause for human approval."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0

    def delay_for(self, attempt_number: int) -> float:
        return min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(0, attempt_number - 1)),
        )

    def should_retry(self, error: Exception, attempt_number: int) -> bool:
        return (
            attempt_number < self.max_attempts
            and not isinstance(error, (NonRetryableExecutionError, ApprovalRequired))
        )
