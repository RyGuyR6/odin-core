#!/usr/bin/env bash

set -Eeuo pipefail

################################################################################
# Odin Milestone 11 v1.0
# Event Bus, Background Job Engine, and Live Event API
################################################################################

SCRIPT_NAME="$(basename "$0")"

handle_error() {
    local exit_code=$?
    local line_number="${1:-unknown}"

    echo
    echo "============================================================"
    echo "❌ MILESTONE 11 FAILED"
    echo "Script: ${SCRIPT_NAME}"
    echo "Line:   ${line_number}"
    echo "Exit:   ${exit_code}"
    echo "============================================================"
    echo
    echo "Backups are available under:"
    echo "  .odin-backups/milestone11/"
    echo

    exit "${exit_code}"
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

log "ODIN MILESTONE 11 — EVENT BUS AND JOB ENGINE"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
BACKUP_DIR="${REPO_ROOT}/.odin-backups/milestone11"

step "Checking repository structure"

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
    echo "Git repository was not found at:"
    echo "  ${REPO_ROOT}"
    exit 1
fi

if [[ ! -d "${BACKEND_DIR}/app" ]]; then
    echo "Odin backend was not found at:"
    echo "  ${BACKEND_DIR}"
    exit 1
fi

cd "${BACKEND_DIR}"

CURRENT_BRANCH="$(git -C "${REPO_ROOT}" branch --show-current)"

echo "Repository: ${REPO_ROOT}"
echo "Backend:    ${BACKEND_DIR}"
echo "Branch:     ${CURRENT_BRANCH}"

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
    echo "Python is not available."
    exit 1
fi

echo "Python: $(command -v "${PYTHON_BIN}")"
"${PYTHON_BIN}" --version

success "Python detected"

################################################################################
# Prepare directories and backups
################################################################################

step "Preparing directories"

mkdir -p app/events
mkdir -p app/jobs
mkdir -p app/api
mkdir -p "${BACKUP_DIR}"

success "Directories prepared"

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

step "Backing up files"

backup_file "app/events/__init__.py"
backup_file "app/events/models.py"
backup_file "app/events/bus.py"
backup_file "app/jobs/__init__.py"
backup_file "app/jobs/models.py"
backup_file "app/jobs/manager.py"
backup_file "app/jobs/service.py"
backup_file "app/api/jobs.py"
backup_file "app/api/events.py"
backup_file "app/planning/executor.py"
backup_file "app/main.py"

success "Backup complete"

################################################################################
# Event package
################################################################################

step "Writing app/events/models.py"

cat > app/events/models.py <<'PY'
"""Event models used throughout Odin."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    """An immutable event emitted by Odin."""

    type: str
    source: str

    payload: dict[str, Any] = field(default_factory=dict)

    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable event representation."""
        return asdict(self)
PY

success "Created app/events/models.py"

step "Writing app/events/bus.py"

cat > app/events/bus.py <<'PY'
"""Thread-safe publish-and-subscribe event bus for Odin."""

from collections import defaultdict, deque
from collections.abc import Callable
from threading import Condition, RLock
from typing import Any

from app.events.models import Event


EventHandler = Callable[[Event], None]


class EventBus:
    """Publishes events and maintains a bounded in-memory event history."""

    def __init__(self, history_limit: int = 1000) -> None:
        if history_limit < 1:
            raise ValueError("Event history limit must be positive.")

        self._history: deque[Event] = deque(maxlen=history_limit)
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

        self._lock = RLock()
        self._condition = Condition(self._lock)

    def publish(
        self,
        event_type: str,
        *,
        source: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Event:
        """Create, store, and dispatch an event."""
        if not event_type or not event_type.strip():
            raise ValueError("Event type cannot be empty.")

        if not source or not source.strip():
            raise ValueError("Event source cannot be empty.")

        event = Event(
            type=event_type.strip(),
            source=source.strip(),
            payload=dict(payload or {}),
            correlation_id=correlation_id,
        )

        with self._condition:
            self._history.append(event)

            handlers = [
                *self._subscribers.get(event.type, []),
                *self._subscribers.get("*", []),
            ]

            self._condition.notify_all()

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Event handlers must not be allowed to break publishers.
                continue

        return event

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Subscribe a handler to an event type or wildcard."""
        if not event_type:
            raise ValueError("Event type cannot be empty.")

        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Remove an event subscription."""
        with self._lock:
            handlers = self._subscribers.get(event_type, [])

            if handler in handlers:
                handlers.remove(handler)

            if not handlers:
                self._subscribers.pop(event_type, None)

    def history(
        self,
        *,
        event_type: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Return recent events matching optional filters."""
        if limit < 1:
            raise ValueError("Event limit must be positive.")

        with self._lock:
            events = list(self._history)

        if event_type:
            events = [event for event in events if event.type == event_type]

        if source:
            events = [event for event in events if event.source == source]

        if correlation_id:
            events = [
                event
                for event in events
                if event.correlation_id == correlation_id
            ]

        return events[-limit:]

    def after(
        self,
        event_id: str | None,
        *,
        limit: int = 100,
    ) -> list[Event]:
        """Return events occurring after a particular event."""
        with self._lock:
            events = list(self._history)

        if event_id is None:
            return events[-limit:]

        for index, event in enumerate(events):
            if event.id == event_id:
                return events[index + 1:index + 1 + limit]

        return events[-limit:]

    def wait_for_events(
        self,
        event_id: str | None,
        *,
        timeout: float = 15.0,
        limit: int = 100,
    ) -> list[Event]:
        """Wait until events newer than event_id are available."""
        with self._condition:
            events = self.after(event_id, limit=limit)

            if events:
                return events

            self._condition.wait(timeout=timeout)

            return self.after(event_id, limit=limit)

    def clear(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history.clear()

    def count(self) -> int:
        """Return the number of retained events."""
        with self._lock:
            return len(self._history)


event_bus = EventBus()
PY

success "Created app/events/bus.py"

step "Writing app/events/__init__.py"

cat > app/events/__init__.py <<'PY'
"""Odin event infrastructure."""

from app.events.bus import EventBus, event_bus
from app.events.models import Event

__all__ = [
    "Event",
    "EventBus",
    "event_bus",
]
PY

success "Created app/events/__init__.py"

################################################################################
# Job package
################################################################################

step "Writing app/jobs/models.py"

cat > app/jobs/models.py <<'PY'
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
PY

success "Created app/jobs/models.py"

step "Writing app/jobs/manager.py"

cat > app/jobs/manager.py <<'PY'
"""Thread-safe in-memory job manager."""

from threading import RLock
from typing import Any

from app.events.bus import EventBus, event_bus
from app.jobs.models import Job


class JobManager:
    """Creates, stores, updates, and publishes state for Odin jobs."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()
        self._bus = bus or event_bus

    def create(
        self,
        tool: str,
        payload: dict[str, Any] | None = None,
        *,
        context_id: str | None = None,
    ) -> Job:
        if not tool or not tool.strip():
            raise ValueError("Job tool cannot be empty.")

        job = Job(
            tool=tool.strip(),
            payload=dict(payload or {}),
            context_id=context_id,
        )

        with self._lock:
            self._jobs[job.id] = job

        self._publish("job.created", job)

        return job

    def exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)

        if job is None:
            raise KeyError(f"Job not found: {job_id}")

        return job

    def instances(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def snapshots(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.instances()]

    def start(self, job_id: str) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.start()

        self._publish("job.started", job)

        return job

    def update_progress(
        self,
        job_id: str,
        progress: int,
        message: str | None = None,
    ) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.update_progress(progress, message)

        self._publish("job.progress", job)

        return job

    def complete(self, job_id: str, result: Any) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.complete(result)

        self._publish("job.completed", job)

        return job

    def fail(
        self,
        job_id: str,
        error: str | Exception,
    ) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.fail(error)

        self._publish("job.failed", job)

        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)

        with self._lock:
            job.cancel()

        self._publish("job.cancelled", job)

        return job

    def delete(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.pop(job_id, None)

        if job is None:
            raise KeyError(f"Job not found: {job_id}")

        self._bus.publish(
            "job.deleted",
            source="job_manager",
            correlation_id=job.id,
            payload={
                "job_id": job.id,
                "tool": job.tool,
            },
        )

        return job

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)

    def _publish(self, event_type: str, job: Job) -> None:
        self._bus.publish(
            event_type,
            source="job_manager",
            correlation_id=job.id,
            payload=job.to_dict(),
        )


manager = JobManager()
PY

success "Created app/jobs/manager.py"

step "Writing app/jobs/service.py"

cat > app/jobs/service.py <<'PY'
"""Background execution service for Odin jobs."""

from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Any

from app.core.executor import executor
from app.jobs.manager import JobManager, manager
from app.jobs.models import Job


class JobService:
    """Runs Odin tool calls in a background thread pool."""

    def __init__(
        self,
        job_manager: JobManager | None = None,
        *,
        max_workers: int = 4,
    ) -> None:
        self._manager = job_manager or manager
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="odin-job",
        )
        self._futures: dict[str, Future[Any]] = {}
        self._lock = RLock()

    def submit(
        self,
        tool: str,
        payload: dict[str, Any] | None = None,
        *,
        context_id: str | None = None,
    ) -> Job:
        job = self._manager.create(
            tool=tool,
            payload=payload,
            context_id=context_id,
        )

        future = self._pool.submit(self._execute, job.id)

        with self._lock:
            self._futures[job.id] = future

        future.add_done_callback(
            lambda _: self._remove_future(job.id)
        )

        return job

    def _execute(self, job_id: str) -> None:
        job = self._manager.start(job_id)

        try:
            self._manager.update_progress(
                job_id,
                10,
                f"Executing tool: {job.tool}",
            )

            result = executor.execute(
                job.tool,
                **job.payload,
            )

            self._manager.complete(
                job_id,
                result,
            )

        except Exception as exc:
            self._manager.fail(
                job_id,
                exc,
            )

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            future = self._futures.get(job_id)

        if future is not None and future.cancel():
            return self._manager.cancel(job_id)

        job = self._manager.get(job_id)

        if job.status == "queued":
            return self._manager.cancel(job_id)

        raise ValueError(
            "The job is already running and cannot be force-cancelled."
        )

    def future_exists(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._futures

    def _remove_future(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)


job_service = JobService()
PY

success "Created app/jobs/service.py"

step "Writing app/jobs/__init__.py"

cat > app/jobs/__init__.py <<'PY'
"""Odin background job infrastructure."""

from app.jobs.manager import JobManager, manager
from app.jobs.models import Job
from app.jobs.service import JobService, job_service

__all__ = [
    "Job",
    "JobManager",
    "JobService",
    "job_service",
    "manager",
]
PY

success "Created app/jobs/__init__.py"

################################################################################
# Jobs API
################################################################################

step "Writing app/api/jobs.py"

cat > app/api/jobs.py <<'PY'
"""HTTP API for Odin background jobs."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.jobs.manager import manager
from app.jobs.service import job_service


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


class CreateJobRequest(BaseModel):
    tool: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    context_id: str | None = None


def job_or_404(job_id: str):
    try:
        return manager.get(job_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post("/", status_code=202)
def create_job(request: CreateJobRequest):
    try:
        job = job_service.submit(
            tool=request.tool,
            payload=request.payload,
            context_id=request.context_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return job.to_dict()


@router.get("/")
def list_jobs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    jobs = manager.instances()

    if status:
        jobs = [job for job in jobs if job.status == status]

    return {
        "count": len(jobs[-limit:]),
        "jobs": [
            job.to_dict()
            for job in jobs[-limit:]
        ],
    }


@router.get("/{job_id}")
def get_job(job_id: str):
    return job_or_404(job_id).to_dict()


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    job_or_404(job_id)

    try:
        return job_service.cancel(job_id).to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.delete("/{job_id}")
def delete_job(job_id: str):
    job = job_or_404(job_id)

    if job.status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail="Active jobs cannot be deleted.",
        )

    return manager.delete(job_id).to_dict()
PY

success "Created app/api/jobs.py"

################################################################################
# Events API and SSE
################################################################################

step "Writing app/api/events.py"

cat > app/api/events.py <<'PY'
"""HTTP and Server-Sent Event APIs for Odin events."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.events.bus import event_bus


router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


@router.get("/")
def list_events(
    event_type: str | None = None,
    source: str | None = None,
    correlation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    events = event_bus.history(
        event_type=event_type,
        source=source,
        correlation_id=correlation_id,
        limit=limit,
    )

    return {
        "count": len(events),
        "events": [
            event.to_dict()
            for event in events
        ],
    }


@router.get("/stream")
async def stream_events(
    request: Request,
    last_event_id: str | None = None,
):
    async def event_generator() -> AsyncIterator[str]:
        cursor = last_event_id

        yield "retry: 3000\n\n"

        while True:
            if await request.is_disconnected():
                break

            events = await asyncio.to_thread(
                event_bus.wait_for_events,
                cursor,
                timeout=15.0,
                limit=100,
            )

            if not events:
                yield ": keep-alive\n\n"
                continue

            for event in events:
                cursor = event.id
                data = json.dumps(
                    event.to_dict(),
                    default=str,
                )

                yield (
                    f"id: {event.id}\n"
                    f"event: {event.type}\n"
                    f"data: {data}\n\n"
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
PY

success "Created app/api/events.py"

################################################################################
# Planner integration
################################################################################

step "Writing enhanced planner executor"

cat > app/planning/executor.py <<'PY'
"""Execution-plan runner with context and event tracking."""

from app.context.service import context_service
from app.core.executor import executor
from app.events.bus import event_bus


class PlanExecutor:
    """Executes a plan while recording context and event history."""

    def execute(
        self,
        plan,
        context_id: str | None = None,
    ):
        if context_id:
            context = context_service.get(context_id)
        else:
            context = context_service.create(
                goal=plan.goal,
            )

        context.set_status("running")

        event_bus.publish(
            "plan.started",
            source="plan_executor",
            correlation_id=context.id,
            payload={
                "context_id": context.id,
                "goal": plan.goal,
                "step_count": len(plan.steps),
            },
        )

        try:
            for index, step in enumerate(
                plan.steps,
                start=context.current_step,
            ):
                event_bus.publish(
                    "plan.step.started",
                    source="plan_executor",
                    correlation_id=context.id,
                    payload={
                        "context_id": context.id,
                        "step": index,
                        "tool": step.tool,
                        "parameters": step.parameters,
                    },
                )

                result = executor.execute(
                    step.tool,
                    **step.parameters,
                )

                context.add_result(
                    step=index,
                    tool=step.tool,
                    result=result,
                )

                event_bus.publish(
                    "plan.step.completed",
                    source="plan_executor",
                    correlation_id=context.id,
                    payload={
                        "context_id": context.id,
                        "step": index,
                        "tool": step.tool,
                        "result": result,
                    },
                )

            context.set_status("completed")

            event_bus.publish(
                "plan.completed",
                source="plan_executor",
                correlation_id=context.id,
                payload=context.to_dict(),
            )

        except Exception as exc:
            context.set_error(exc)

            event_bus.publish(
                "plan.failed",
                source="plan_executor",
                correlation_id=context.id,
                payload={
                    "context_id": context.id,
                    "goal": plan.goal,
                    "error": str(exc),
                },
            )

            raise

        return context


plan_executor = PlanExecutor()
PY

success "Enhanced planner executor"

################################################################################
# Patch main.py
################################################################################

step "Registering events API in app/main.py"

"${PYTHON_BIN}" - <<'PY'
from pathlib import Path


path = Path("app/main.py")
text = path.read_text()

import_line = "from app.api.events import router as events_router"
include_line = "app.include_router(events_router)"

if import_line not in text:
    anchor_candidates = [
        "from app.api.health import router as health_router",
        "from fastapi import FastAPI",
    ]

    for anchor in anchor_candidates:
        if anchor in text:
            text = text.replace(
                anchor,
                f"{anchor}\n{import_line}",
                1,
            )
            break
    else:
        raise RuntimeError(
            "Could not find a safe import anchor in app/main.py"
        )

if include_line not in text:
    anchor_candidates = [
        "app.include_router(jobs_router)",
        "app.include_router(health_router)",
    ]

    for anchor in anchor_candidates:
        if anchor in text:
            text = text.replace(
                anchor,
                f"{anchor}\n{include_line}",
                1,
            )
            break
    else:
        mount_anchor = 'app.mount("/mcp"'

        if mount_anchor in text:
            text = text.replace(
                mount_anchor,
                f"{include_line}\n\n{mount_anchor}",
                1,
            )
        else:
            raise RuntimeError(
                "Could not find a safe router anchor in app/main.py"
            )

path.write_text(text)

print("Events router registered.")
PY

success "Events API registered"

################################################################################
# Ignore backup files
################################################################################

step "Updating .gitignore"

touch "${REPO_ROOT}/.gitignore"

grep -qxF '.odin-backups/' "${REPO_ROOT}/.gitignore" \
    || echo '.odin-backups/' >> "${REPO_ROOT}/.gitignore"

grep -qxF '__pycache__/' "${REPO_ROOT}/.gitignore" \
    || echo '__pycache__/' >> "${REPO_ROOT}/.gitignore"

grep -qxF '*.py[cod]' "${REPO_ROOT}/.gitignore" \
    || echo '*.py[cod]' >> "${REPO_ROOT}/.gitignore"

success ".gitignore updated"

################################################################################
# Syntax validation
################################################################################

log "VALIDATING MILESTONE 11"

step "Compiling milestone files"

"${PYTHON_BIN}" -m py_compile \
    app/events/__init__.py \
    app/events/models.py \
    app/events/bus.py \
    app/jobs/__init__.py \
    app/jobs/models.py \
    app/jobs/manager.py \
    app/jobs/service.py \
    app/api/jobs.py \
    app/api/events.py \
    app/planning/executor.py \
    app/main.py

success "Python syntax validation passed"

################################################################################
# Event bus tests
################################################################################

step "Testing event bus"

"${PYTHON_BIN}" - <<'PY'
from app.events.bus import EventBus


bus = EventBus(history_limit=10)
received = []


def handler(event):
    received.append(event)


bus.subscribe("test.created", handler)

event = bus.publish(
    "test.created",
    source="milestone11",
    correlation_id="test-correlation",
    payload={"working": True},
)

assert event.type == "test.created"
assert event.source == "milestone11"
assert event.payload["working"] is True
assert event.correlation_id == "test-correlation"
assert bus.count() == 1
assert len(received) == 1
assert received[0].id == event.id

history = bus.history(
    event_type="test.created",
)

assert len(history) == 1
assert history[0].id == event.id

bus.unsubscribe("test.created", handler)

bus.publish(
    "test.created",
    source="milestone11",
)

assert len(received) == 1

print("Event bus tests passed.")
PY

success "Event bus tests passed"

################################################################################
# Job manager tests
################################################################################

step "Testing job manager"

"${PYTHON_BIN}" - <<'PY'
from app.events.bus import EventBus
from app.jobs.manager import JobManager


bus = EventBus()
manager = JobManager(bus)

job = manager.create(
    "health",
    {"verbose": True},
    context_id="context-test",
)

assert job.status == "queued"
assert job.progress == 0
assert manager.exists(job.id)
assert manager.count() == 1

manager.start(job.id)

assert job.status == "running"
assert job.started_at is not None

manager.update_progress(
    job.id,
    50,
    "Halfway complete",
)

assert job.progress == 50
assert job.message == "Halfway complete"

manager.complete(
    job.id,
    {"status": "ok"},
)

assert job.status == "completed"
assert job.progress == 100
assert job.result == {"status": "ok"}
assert job.completed_at is not None

event_types = [
    event.type
    for event in bus.history(limit=20)
]

assert event_types == [
    "job.created",
    "job.started",
    "job.progress",
    "job.completed",
]

snapshot = manager.get(job.id).to_dict()

assert snapshot["id"] == job.id
assert snapshot["status"] == "completed"

deleted = manager.delete(job.id)

assert deleted.id == job.id
assert manager.count() == 0

print("Job manager tests passed.")
PY

success "Job manager tests passed"

################################################################################
# API import test
################################################################################

step "Testing API imports and route registration"

"${PYTHON_BIN}" - <<'TESTPY'
from app.main import app


# OpenAPI is the authoritative flattened view of FastAPI routes.
schema = app.openapi()
paths = set(schema.get("paths", {}))

required_paths = {
    "/jobs/",
    "/jobs/{job_id}",
    "/events/",
    "/events/stream",
}

missing = required_paths - paths

if missing:
    print("Discovered OpenAPI routes:")
    for route_path in sorted(paths):
        print(f"  {route_path}")
    raise AssertionError(f"Missing API routes: {sorted(missing)}")

print("Registered milestone routes:")
for route_path in sorted(required_paths):
    print(f"  {route_path}")
TESTPY

success "API route test passed"

################################################################################
# Full backend compilation
################################################################################

step "Compiling full Odin backend"

"${PYTHON_BIN}" -m compileall -q app

success "Full backend compilation passed"

################################################################################
# Cleanup generated tracked caches
################################################################################

step "Restoring tracked Python cache files"

git -C "${REPO_ROOT}" status --porcelain \
    | awk '$1 == "M" && $2 ~ /__pycache__\/.*\.pyc$/ {print $2}' \
    | while IFS= read -r cache_file; do
        if [[ -n "${cache_file}" ]]; then
            git -C "${REPO_ROOT}" restore -- "${cache_file}"
            echo "Restored: ${cache_file}"
        fi
    done

success "Tracked cache cleanup complete"

################################################################################
# Completion summary
################################################################################

log "MILESTONE 11 COMPLETE"

echo "Added or upgraded:"
echo "  backend/app/events/models.py"
echo "  backend/app/events/bus.py"
echo "  backend/app/events/__init__.py"
echo "  backend/app/jobs/models.py"
echo "  backend/app/jobs/manager.py"
echo "  backend/app/jobs/service.py"
echo "  backend/app/jobs/__init__.py"
echo "  backend/app/api/jobs.py"
echo "  backend/app/api/events.py"
echo "  backend/app/planning/executor.py"
echo "  backend/app/main.py"
echo
echo "New capabilities:"
echo "  • Thread-safe application event bus"
echo "  • Bounded event history"
echo "  • Event subscriptions"
echo "  • Background tool execution"
echo "  • Job progress and lifecycle tracking"
echo "  • Job cancellation support"
echo "  • Planner execution events"
echo "  • Event history REST API"
echo "  • Live Server-Sent Events stream"
echo
echo "Live event endpoint:"
echo "  GET /events/stream"
echo
echo "Backups:"
echo "  .odin-backups/milestone11/"
echo
echo "Git status:"
git -C "${REPO_ROOT}" status --short
echo
echo "✅ Odin Milestone 11 installed successfully."
echo "Review the changes before committing."
