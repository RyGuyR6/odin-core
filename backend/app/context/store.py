"""Thread-safe in-memory storage for execution contexts."""

from threading import RLock
from typing import Any

from app.context.models import ExecutionContext


class ContextStore:
    """Stores Odin execution contexts in memory."""

    def __init__(self) -> None:
        self._contexts: dict[str, ExecutionContext] = {}
        self._lock = RLock()

    def create(
        self,
        goal: str,
        variables: dict[str, Any] | None = None,
    ) -> ExecutionContext:
        """Create and store a new execution context."""
        if not goal or not goal.strip():
            raise ValueError("Context goal cannot be empty.")

        context = ExecutionContext(
            goal=goal.strip(),
            variables=dict(variables or {}),
        )

        with self._lock:
            self._contexts[context.id] = context

        return context

    def add(self, context: ExecutionContext) -> ExecutionContext:
        """Add an existing context to the store."""
        with self._lock:
            if context.id in self._contexts:
                raise ValueError(
                    f"Execution context already exists: {context.id}"
                )

            self._contexts[context.id] = context

        return context

    def exists(self, context_id: str) -> bool:
        """Return whether a context exists."""
        with self._lock:
            return context_id in self._contexts

    def get(self, context_id: str) -> ExecutionContext:
        """Return a context by identifier."""
        with self._lock:
            context = self._contexts.get(context_id)

        if context is None:
            raise KeyError(f"Execution context not found: {context_id}")

        return context

    def instances(self) -> list[ExecutionContext]:
        """Return all stored context instances."""
        with self._lock:
            return list(self._contexts.values())

    def snapshots(self) -> list[dict[str, Any]]:
        """Return serializable snapshots of all contexts."""
        return [context.to_dict() for context in self.instances()]

    def delete(self, context_id: str) -> ExecutionContext:
        """Delete and return a stored context."""
        with self._lock:
            context = self._contexts.pop(context_id, None)

        if context is None:
            raise KeyError(f"Execution context not found: {context_id}")

        return context

    def clear(self) -> None:
        """Remove every context from the store."""
        with self._lock:
            self._contexts.clear()

    def count(self) -> int:
        """Return the number of stored contexts."""
        with self._lock:
            return len(self._contexts)


context_store = ContextStore()
