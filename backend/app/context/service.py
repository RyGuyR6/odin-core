"""Service layer for Odin execution contexts."""

from typing import Any

from app.context.models import ExecutionContext
from app.context.store import ContextStore, context_store


class ContextService:
    """Coordinates execution-context operations."""

    def __init__(self, store: ContextStore | None = None) -> None:
        self._store = store or context_store

    def create(
        self,
        goal: str,
        variables: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        """Create a new execution context."""
        return self._store.create(
            goal=goal,
            variables=variables,
        )

    def get(self, context_id: str) -> ExecutionContext:
        """Return an execution context."""
        return self._store.get(context_id)

    def exists(self, context_id: str) -> bool:
        """Return whether an execution context exists."""
        return self._store.exists(context_id)

    def instances(self) -> list[ExecutionContext]:
        """Return all execution contexts."""
        return self._store.instances()

    def snapshots(self) -> list[dict[str, Any]]:
        """Return all contexts as serializable dictionaries."""
        return self._store.snapshots()

    def set_status(
        self,
        context_id: str,
        status: str,
    ) -> ExecutionContext:
        """Update a context status."""
        context = self.get(context_id)
        context.set_status(status)
        return context

    def set_variable(
        self,
        context_id: str,
        name: str,
        value: Any,
    ) -> ExecutionContext:
        """Set a context variable."""
        context = self.get(context_id)
        context.set_variable(name, value)
        return context

    def add_result(
        self,
        context_id: str,
        *,
        step: int,
        tool: str,
        result: Any,
    ) -> ExecutionContext:
        """Record an execution result."""
        context = self.get(context_id)
        context.add_result(
            step=step,
            tool=tool,
            result=result,
        )
        return context

    def set_error(
        self,
        context_id: str,
        error: str | Exception,
    ) -> ExecutionContext:
        """Mark a context as failed."""
        context = self.get(context_id)
        context.set_error(error)
        return context

    def delete(self, context_id: str) -> ExecutionContext:
        """Delete an execution context."""
        return self._store.delete(context_id)

    def clear(self) -> None:
        """Delete every execution context."""
        self._store.clear()

    def count(self) -> int:
        """Return the number of execution contexts."""
        return self._store.count()


context_service = ContextService()
