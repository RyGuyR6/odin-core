"""Data models for Odin execution contexts."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExecutionContext:
    """Stores state and results for an Odin execution."""

    goal: str

    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "created"
    current_step: int = 0

    variables: dict[str, Any] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)

    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    error: str | None = None

    def touch(self) -> None:
        """Update the context modification timestamp."""
        self.updated_at = utc_now()

    def set_status(self, status: str) -> None:
        """Update the current execution status."""
        if not status or not status.strip():
            raise ValueError("Context status cannot be empty.")

        self.status = status.strip()
        self.touch()

    def set_variable(self, name: str, value: Any) -> None:
        """Store a named context variable."""
        if not name or not name.strip():
            raise ValueError("Variable name cannot be empty.")

        self.variables[name.strip()] = value
        self.touch()

    def remove_variable(self, name: str) -> Any:
        """Remove and return a stored context variable."""
        if name not in self.variables:
            raise KeyError(f"Context variable not found: {name}")

        value = self.variables.pop(name)
        self.touch()
        return value

    def get_variable(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """Return a context variable or a default value."""
        return self.variables.get(name, default)

    def add_result(
        self,
        *,
        step: int,
        tool: str,
        result: Any,
    ) -> dict[str, Any]:
        """Record the result produced by an execution step."""
        if step < 0:
            raise ValueError("Step number cannot be negative.")

        if not tool or not tool.strip():
            raise ValueError("Tool name cannot be empty.")

        entry = {
            "step": step,
            "tool": tool.strip(),
            "result": result,
            "recorded_at": utc_now(),
        }

        self.results.append(entry)
        self.current_step = step + 1
        self.touch()

        return entry

    def set_error(self, error: str | Exception) -> None:
        """Store an execution error and mark the context as failed."""
        self.error = str(error)
        self.status = "failed"
        self.touch()

    def clear_error(self) -> None:
        """Clear a previously stored execution error."""
        self.error = None
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        """Convert the context to a serializable dictionary."""
        return asdict(self)
