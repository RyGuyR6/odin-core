#!/usr/bin/env bash

set -Eeuo pipefail

################################################################################
# Odin Milestone 10
# Execution Context and Memory Foundation
################################################################################

SCRIPT_NAME="$(basename "$0")"

handle_error() {
    local exit_code=$?
    local line_number="${1:-unknown}"

    echo
    echo "============================================================"
    echo "❌ Milestone 10 failed"
    echo "Script: ${SCRIPT_NAME}"
    echo "Line:   ${line_number}"
    echo "Exit:   ${exit_code}"
    echo "============================================================"
    echo

    exit "$exit_code"
}

trap 'handle_error $LINENO' ERR

log() {
    echo
    echo "============================================================"
    echo "$1"
    echo "============================================================"
}

step() {
    echo
    echo "▶ $1"
}

success() {
    echo "✅ $1"
}

################################################################################
# Locate repository
################################################################################

log "ODIN MILESTONE 10 — EXECUTION CONTEXT FOUNDATION"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

step "Checking repository location"

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
    echo "Repository root was not found at:"
    echo "${REPO_ROOT}"
    exit 1
fi

if [[ ! -d "${BACKEND_DIR}/app" ]]; then
    echo "Odin backend was not found at:"
    echo "${BACKEND_DIR}"
    exit 1
fi

cd "${BACKEND_DIR}"

echo "Repository: ${REPO_ROOT}"
echo "Backend:    ${BACKEND_DIR}"
echo "Branch:     $(git -C "${REPO_ROOT}" branch --show-current)"
success "Repository located"

################################################################################
# Python detection
################################################################################

step "Detecting Python"

if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "Python is not installed or is not available in PATH."
    exit 1
fi

echo "Python executable: $(command -v "${PYTHON_BIN}")"
"${PYTHON_BIN}" --version
success "Python detected"

################################################################################
# Prepare directories
################################################################################

step "Creating context package"

mkdir -p app/context
mkdir -p "${REPO_ROOT}/.odin-backups/milestone10"

BACKUP_DIR="${REPO_ROOT}/.odin-backups/milestone10"

success "Directories prepared"

################################################################################
# Backup existing files
################################################################################

backup_file() {
    local relative_path="$1"
    local source_path="${BACKEND_DIR}/${relative_path}"
    local backup_path="${BACKUP_DIR}/${relative_path}"

    if [[ -f "${source_path}" ]]; then
        mkdir -p "$(dirname "${backup_path}")"
        cp "${source_path}" "${backup_path}"
        echo "Backed up: ${relative_path}"
    fi
}

step "Backing up existing context files"

backup_file "app/context/__init__.py"
backup_file "app/context/models.py"
backup_file "app/context/store.py"
backup_file "app/context/service.py"

success "Backup step complete"

################################################################################
# app/context/__init__.py
################################################################################

step "Writing app/context/__init__.py"

cat > app/context/__init__.py <<'PY'
"""Execution context and memory support for Odin."""

from app.context.models import ExecutionContext
from app.context.service import ContextService, context_service
from app.context.store import ContextStore, context_store

__all__ = [
    "ContextService",
    "ContextStore",
    "ExecutionContext",
    "context_service",
    "context_store",
]
PY

success "Created app/context/__init__.py"

################################################################################
# app/context/models.py
################################################################################

step "Writing app/context/models.py"

cat > app/context/models.py <<'PY'
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
PY

success "Created app/context/models.py"

################################################################################
# app/context/store.py
################################################################################

step "Writing app/context/store.py"

cat > app/context/store.py <<'PY'
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
PY

success "Created app/context/store.py"

################################################################################
# app/context/service.py
################################################################################

step "Writing app/context/service.py"

cat > app/context/service.py <<'PY'
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
PY

success "Created app/context/service.py"

################################################################################
# Syntax validation
################################################################################

log "VALIDATING PYTHON FILES"

step "Compiling execution context package"

"${PYTHON_BIN}" -m py_compile \
    app/context/__init__.py \
    app/context/models.py \
    app/context/store.py \
    app/context/service.py

success "Python syntax validation passed"

################################################################################
# Import test
################################################################################

step "Testing package imports"

"${PYTHON_BIN}" - <<'PY'
from app.context import (
    ContextService,
    ContextStore,
    ExecutionContext,
    context_service,
    context_store,
)

assert ContextService is not None
assert ContextStore is not None
assert ExecutionContext is not None
assert context_service is not None
assert context_store is not None

print("Package imports passed.")
PY

success "Import test passed"

################################################################################
# Functional tests
################################################################################

log "RUNNING EXECUTION CONTEXT TESTS"

"${PYTHON_BIN}" - <<'PY'
from app.context.service import ContextService
from app.context.store import ContextStore


store = ContextStore()
service = ContextService(store)


context = service.create(
    goal="Verify Odin execution context foundation",
    variables={
        "repository": "RyGuyR6/odin-core",
        "branch": "feature/mcp-foundation",
    },
)

assert context.goal == "Verify Odin execution context foundation"
assert context.status == "created"
assert context.current_step == 0
assert service.count() == 1
assert service.exists(context.id)

service.set_status(context.id, "running")

assert context.status == "running"

service.set_variable(
    context.id,
    "environment",
    "test",
)

assert context.get_variable("environment") == "test"

service.add_result(
    context.id,
    step=0,
    tool="health",
    result={
        "status": "ok",
    },
)

assert context.current_step == 1
assert len(context.results) == 1
assert context.results[0]["tool"] == "health"

service.add_result(
    context.id,
    step=1,
    tool="github_repository",
    result={
        "repository": "RyGuyR6/odin-core",
    },
)

assert context.current_step == 2
assert len(context.results) == 2

service.set_status(context.id, "completed")

assert context.status == "completed"
assert context.error is None

snapshot = context.to_dict()

assert snapshot["id"] == context.id
assert snapshot["status"] == "completed"
assert snapshot["current_step"] == 2
assert len(snapshot["results"]) == 2

snapshots = service.snapshots()

assert len(snapshots) == 1
assert snapshots[0]["id"] == context.id

deleted = service.delete(context.id)

assert deleted.id == context.id
assert service.count() == 0
assert not service.exists(context.id)

print()
print("Execution context functional tests passed.")
print(f"Test context ID: {context.id}")
print(f"Final status:    {context.status}")
print(f"Recorded steps:  {context.current_step}")
PY

success "Execution context functional tests passed"

################################################################################
# Existing backend compilation
################################################################################

log "CHECKING BACKEND COMPATIBILITY"

step "Compiling the Odin application"

"${PYTHON_BIN}" -m compileall -q app

success "Odin application compiled successfully"

################################################################################
# Git summary
################################################################################

log "MILESTONE 10 COMPLETE"

echo "Created or updated:"
echo "  backend/app/context/__init__.py"
echo "  backend/app/context/models.py"
echo "  backend/app/context/store.py"
echo "  backend/app/context/service.py"
echo
echo "Backups, when required:"
echo "  .odin-backups/milestone10/"
echo
echo "Git status:"
git -C "${REPO_ROOT}" status --short
echo
echo "✅ Execution Context Foundation installed successfully."
echo
echo "Do not commit yet unless the files above are the only intended changes."