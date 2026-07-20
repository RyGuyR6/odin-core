#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.9"
ROOT="${ROOT:-/workspaces/odin-core}"
BACKEND="$ROOT/backend"
PYTHON_BIN="$BACKEND/.venv/bin/python"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_9/$STAMP"
CHECKS=0
ROLLED_BACK=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ printf '✅ %s\n' "$1"; CHECKS=$((CHECKS+1)); }
fail(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  [[ "$ROLLED_BACK" -eq 1 ]] && return
  ROLLED_BACK=1
  printf '\n↩ Rolling back Milestone %s changes...\n' "$MILESTONE"
  if [[ -d "$BACKUP_DIR/files" ]]; then
    while IFS= read -r -d '' f; do
      rel="${f#"$BACKUP_DIR/files/"}"
      mkdir -p "$(dirname "$ROOT/$rel")"
      cp -a "$f" "$ROOT/$rel"
    done < <(find "$BACKUP_DIR/files" -type f -print0)
  fi
  if [[ -f "$BACKUP_DIR/created.list" ]]; then
    while IFS= read -r rel; do
      [[ -n "$rel" ]] && rm -f "$ROOT/$rel"
    done < "$BACKUP_DIR/created.list"
  fi
  printf '✅ Rollback completed\n'
}

on_error(){
  code=$?
  line=${BASH_LINENO[0]:-unknown}
  rollback
  printf '\n============================================================\n'
  printf '❌ MILESTONE %s FAILED\nLine: %s\nExit: %s\nBackup: %s\n' \
    "$MILESTONE" "$line" "$code" "$BACKUP_DIR"
  exit "$code"
}
trap on_error ERR

printf '============================================================\n'
printf 'ODIN MILESTONE %s — AUTONOMOUS CHANGE EXECUTION\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"

[[ -d "$ROOT/.git" ]] || fail "Repository not found"
[[ -x "$PYTHON_BIN" ]] || fail "Backend virtualenv Python not found"
[[ -f "$BACKEND/app/main.py" ]] || fail "FastAPI application missing"
[[ -f "$BACKEND/app/services/github/provider.py" ]] || fail "GitHub provider missing"
ok "Milestone 21.8 foundation detected"

mkdir -p "$BACKUP_DIR/files"
: > "$BACKUP_DIR/created.list"

backup_file(){
  rel="${1#"$ROOT/"}"
  if [[ -e "$1" ]]; then
    mkdir -p "$BACKUP_DIR/files/$(dirname "$rel")"
    cp -a "$1" "$BACKUP_DIR/files/$rel"
  else
    printf '%s\n' "$rel" >> "$BACKUP_DIR/created.list"
  fi
}

FILES=(
  "$BACKEND/app/main.py"
  "$BACKEND/app/services/change_tasks.py"
  "$BACKEND/app/api/change_tasks.py"
  "$BACKEND/tests/test_change_task_orchestration.py"
)
for f in "${FILES[@]}"; do backup_file "$f"; done
ok "Backup created at $BACKUP_DIR"

step "Installing autonomous task orchestration service"
cat > "$BACKEND/app/services/change_tasks.py" <<'PY'
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


TERMINAL_TASK_STATES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.ROLLED_BACK,
}


class TaskOrchestrationError(RuntimeError):
    pass


@dataclass
class ChangeStep:
    id: str
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    rollback_action: str | None = None
    rollback_parameters: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    idempotency_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChangeStep":
        data = dict(payload)
        data["status"] = StepStatus(data.get("status", StepStatus.PENDING))
        return cls(**data)


@dataclass
class ChangeTask:
    id: str
    title: str
    description: str
    steps: list[ChangeStep]
    status: TaskStatus = TaskStatus.PLANNED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    current_step: int = 0
    dry_run: bool = True
    confirmed: bool = False
    stop_on_error: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_step": self.current_step,
            "dry_run": self.dry_run,
            "confirmed": self.confirmed,
            "stop_on_error": self.stop_on_error,
            "metadata": self.metadata,
            "history": self.history,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChangeTask":
        data = dict(payload)
        data["status"] = TaskStatus(data.get("status", TaskStatus.PLANNED))
        data["steps"] = [ChangeStep.from_dict(item) for item in data.get("steps", [])]
        return cls(**data)


class JsonTaskStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or ".odin/tasks")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, task_id: str) -> Path:
        if not task_id or "/" in task_id or ".." in task_id:
            raise TaskOrchestrationError("Invalid task id")
        return self.root / f"{task_id}.json"

    def save(self, task: ChangeTask) -> ChangeTask:
        task.updated_at = utc_now()
        path = self._path(task.id)
        temporary = path.with_suffix(".json.tmp")
        with self._lock:
            temporary.write_text(json.dumps(task.to_dict(), indent=2, sort_keys=True))
            temporary.replace(path)
        return task

    def get(self, task_id: str) -> ChangeTask:
        path = self._path(task_id)
        if not path.exists():
            raise TaskOrchestrationError(f"Task not found: {task_id}")
        with self._lock:
            return ChangeTask.from_dict(json.loads(path.read_text()))

    def list(self, limit: int = 100) -> list[ChangeTask]:
        with self._lock:
            paths = sorted(
                self.root.glob("*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            return [
                ChangeTask.from_dict(json.loads(path.read_text()))
                for path in paths[: max(1, min(limit, 500))]
            ]

    def delete(self, task_id: str) -> None:
        path = self._path(task_id)
        with self._lock:
            if path.exists():
                path.unlink()


Action = Callable[[dict[str, Any]], Any]


class ChangeTaskOrchestrator:
    def __init__(self, store: JsonTaskStore | None = None):
        self.store = store or JsonTaskStore()
        self._actions: dict[str, Action] = {}
        self._rollback_actions: dict[str, Action] = {}
        self._lock = threading.RLock()
        self.register_action("echo", self._echo)
        self.register_action("assert", self._assert)
        self.register_action("record", self._record)

    @staticmethod
    def _echo(parameters: dict[str, Any]) -> dict[str, Any]:
        return {"message": parameters.get("message", "")}

    @staticmethod
    def _assert(parameters: dict[str, Any]) -> dict[str, Any]:
        condition = bool(parameters.get("condition"))
        if not condition:
            raise TaskOrchestrationError(
                str(parameters.get("message", "Task assertion failed"))
            )
        return {"passed": True}

    @staticmethod
    def _record(parameters: dict[str, Any]) -> dict[str, Any]:
        return {"recorded": parameters}

    def register_action(
        self,
        name: str,
        action: Action,
        *,
        rollback: Action | None = None,
    ) -> None:
        name = name.strip()
        if not name:
            raise TaskOrchestrationError("Action name is required")
        with self._lock:
            self._actions[name] = action
            if rollback is not None:
                self._rollback_actions[name] = rollback

    def available_actions(self) -> list[str]:
        return sorted(self._actions)

    def create_task(
        self,
        *,
        title: str,
        description: str = "",
        steps: list[dict[str, Any]],
        dry_run: bool = True,
        confirmed: bool = False,
        stop_on_error: bool = True,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> ChangeTask:
        title = title.strip()
        if not title:
            raise TaskOrchestrationError("Task title is required")
        if not steps:
            raise TaskOrchestrationError("At least one task step is required")
        if not dry_run and not confirmed:
            raise TaskOrchestrationError(
                "Explicit confirmation is required for live task execution"
            )

        normalized = []
        seen_ids = set()
        for index, raw in enumerate(steps):
            step_id = str(raw.get("id") or f"step-{index + 1}")
            if step_id in seen_ids:
                raise TaskOrchestrationError(f"Duplicate step id: {step_id}")
            seen_ids.add(step_id)
            action = str(raw.get("action", "")).strip()
            if not action:
                raise TaskOrchestrationError(f"Step {step_id} has no action")
            normalized.append(
                ChangeStep(
                    id=step_id,
                    action=action,
                    parameters=dict(raw.get("parameters") or {}),
                    rollback_action=raw.get("rollback_action"),
                    rollback_parameters=dict(raw.get("rollback_parameters") or {}),
                    idempotency_key=raw.get("idempotency_key"),
                )
            )

        task = ChangeTask(
            id=task_id or uuid.uuid4().hex,
            title=title,
            description=description,
            steps=normalized,
            dry_run=dry_run,
            confirmed=confirmed,
            stop_on_error=stop_on_error,
            metadata=metadata or {},
        )
        self._event(task, "task_planned", {"step_count": len(task.steps)})
        return self.store.save(task)

    def _event(
        self,
        task: ChangeTask,
        event: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        task.history.append(
            {"timestamp": utc_now(), "event": event, "details": details or {}}
        )

    def _completed_idempotency_keys(self, task: ChangeTask) -> set[str]:
        return {
            step.idempotency_key
            for step in task.steps
            if step.idempotency_key and step.status == StepStatus.SUCCEEDED
        }

    def execute(self, task_id: str) -> ChangeTask:
        with self._lock:
            task = self.store.get(task_id)
            if task.status == TaskStatus.SUCCEEDED:
                return task
            if task.status in {TaskStatus.CANCELLED, TaskStatus.ROLLED_BACK}:
                raise TaskOrchestrationError(
                    f"Cannot execute task in state {task.status.value}"
                )
            if not task.dry_run and not task.confirmed:
                raise TaskOrchestrationError(
                    "Explicit confirmation is required for live task execution"
                )

            task.status = TaskStatus.RUNNING
            task.started_at = task.started_at or utc_now()
            task.error = None
            self._event(task, "task_started", {"dry_run": task.dry_run})
            self.store.save(task)

            completed_keys = self._completed_idempotency_keys(task)
            failures = 0

            for index, step in enumerate(task.steps):
                task.current_step = index
                if step.status == StepStatus.SUCCEEDED:
                    continue
                if (
                    step.idempotency_key
                    and step.idempotency_key in completed_keys
                ):
                    step.status = StepStatus.SKIPPED
                    step.completed_at = utc_now()
                    self._event(
                        task,
                        "step_skipped",
                        {"step_id": step.id, "reason": "idempotency"},
                    )
                    self.store.save(task)
                    continue

                step.status = StepStatus.RUNNING
                step.started_at = utc_now()
                step.error = None
                self._event(task, "step_started", {"step_id": step.id})
                self.store.save(task)

                try:
                    if task.dry_run:
                        step.result = {
                            "planned": True,
                            "action": step.action,
                            "parameters": step.parameters,
                        }
                    else:
                        action = self._actions.get(step.action)
                        if action is None:
                            raise TaskOrchestrationError(
                                f"Unknown action: {step.action}"
                            )
                        step.result = action(step.parameters)
                    step.status = StepStatus.SUCCEEDED
                    step.completed_at = utc_now()
                    if step.idempotency_key:
                        completed_keys.add(step.idempotency_key)
                    self._event(task, "step_succeeded", {"step_id": step.id})
                except Exception as exc:
                    failures += 1
                    step.status = StepStatus.FAILED
                    step.error = str(exc)
                    step.completed_at = utc_now()
                    task.error = str(exc)
                    self._event(
                        task,
                        "step_failed",
                        {"step_id": step.id, "error": str(exc)},
                    )
                    self.store.save(task)
                    if task.stop_on_error:
                        task.status = TaskStatus.FAILED
                        task.completed_at = utc_now()
                        self._event(task, "task_failed", {"step_id": step.id})
                        return self.store.save(task)
                self.store.save(task)

            task.completed_at = utc_now()
            task.status = TaskStatus.FAILED if failures else TaskStatus.SUCCEEDED
            self._event(task, f"task_{task.status.value}")
            return self.store.save(task)

    def cancel(self, task_id: str) -> ChangeTask:
        with self._lock:
            task = self.store.get(task_id)
            if task.status in TERMINAL_TASK_STATES:
                return task
            task.status = TaskStatus.CANCELLED
            task.completed_at = utc_now()
            self._event(task, "task_cancelled")
            return self.store.save(task)

    def rollback(self, task_id: str) -> ChangeTask:
        with self._lock:
            task = self.store.get(task_id)
            rollback_failures = []
            for step in reversed(task.steps):
                if step.status != StepStatus.SUCCEEDED:
                    continue
                action_name = step.rollback_action or step.action
                action = self._rollback_actions.get(action_name)
                if task.dry_run:
                    step.status = StepStatus.ROLLED_BACK
                    self._event(
                        task,
                        "step_rollback_planned",
                        {"step_id": step.id},
                    )
                    continue
                if action is None:
                    rollback_failures.append(
                        f"No rollback registered for {action_name}"
                    )
                    continue
                try:
                    action(step.rollback_parameters)
                    step.status = StepStatus.ROLLED_BACK
                    self._event(task, "step_rolled_back", {"step_id": step.id})
                except Exception as exc:
                    rollback_failures.append(f"{step.id}: {exc}")

            if rollback_failures:
                task.status = TaskStatus.FAILED
                task.error = "; ".join(rollback_failures)
                self._event(
                    task,
                    "rollback_failed",
                    {"errors": rollback_failures},
                )
            else:
                task.status = TaskStatus.ROLLED_BACK
                task.completed_at = utc_now()
                self._event(task, "task_rolled_back")
            return self.store.save(task)

    def get(self, task_id: str) -> ChangeTask:
        return self.store.get(task_id)

    def list(self, limit: int = 100) -> list[ChangeTask]:
        return self.store.list(limit=limit)


change_task_orchestrator = ChangeTaskOrchestrator()
PY
ok "Autonomous orchestration service installed"

step "Installing task orchestration API"
cat > "$BACKEND/app/api/change_tasks.py" <<'PY'
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.change_tasks import (
    TaskOrchestrationError,
    change_task_orchestrator,
)

router = APIRouter(prefix="/change-tasks", tags=["Change Tasks"])


class ChangeStepRequest(BaseModel):
    id: str | None = None
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    rollback_action: str | None = None
    rollback_parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ChangeTaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    steps: list[ChangeStepRequest]
    dry_run: bool = True
    confirmed: bool = False
    stop_on_error: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None


def run(fn):
    try:
        return fn()
    except TaskOrchestrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("")
def list_change_tasks(limit: int = Query(default=100, ge=1, le=500)):
    return [task.to_dict() for task in change_task_orchestrator.list(limit)]


@router.get("/actions")
def list_change_task_actions():
    return {"actions": change_task_orchestrator.available_actions()}


@router.post("")
def create_change_task(request: ChangeTaskCreateRequest):
    task = run(
        lambda: change_task_orchestrator.create_task(
            title=request.title,
            description=request.description,
            steps=[step.model_dump() for step in request.steps],
            dry_run=request.dry_run,
            confirmed=request.confirmed,
            stop_on_error=request.stop_on_error,
            metadata=request.metadata,
            task_id=request.task_id,
        )
    )
    return task.to_dict()


@router.get("/{task_id}")
def get_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.get(task_id)).to_dict()


@router.post("/{task_id}/execute")
def execute_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.execute(task_id)).to_dict()


@router.post("/{task_id}/cancel")
def cancel_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.cancel(task_id)).to_dict()


@router.post("/{task_id}/rollback")
def rollback_change_task(task_id: str):
    return run(lambda: change_task_orchestrator.rollback(task_id)).to_dict()
PY
ok "Task orchestration API installed"

step "Registering change-task API"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

path = Path("backend/app/main.py")
text = path.read_text()

import_line = "from app.api.change_tasks import router as change_tasks_router\n"
if import_line not in text:
    anchor = "from app.api.github import router as github_router\n"
    if anchor in text:
        text = text.replace(anchor, anchor + import_line)
    else:
        text = import_line + text

include_line = "app.include_router(change_tasks_router)"
if include_line not in text:
    anchor = "app.include_router(github_router)"
    if anchor in text:
        text = text.replace(anchor, anchor + "\n" + include_line)
    else:
        raise SystemExit("Could not locate router registration in app/main.py")

path.write_text(text)
PY
ok "Change-task API registered"

step "Adding orchestration regression tests"
cat > "$BACKEND/tests/test_change_task_orchestration.py" <<'PY'
from pathlib import Path

import pytest

from app.services.change_tasks import (
    ChangeTaskOrchestrator,
    JsonTaskStore,
    StepStatus,
    TaskOrchestrationError,
    TaskStatus,
)


@pytest.fixture
def orchestrator(tmp_path: Path):
    return ChangeTaskOrchestrator(JsonTaskStore(tmp_path / "tasks"))


def test_task_defaults_to_dry_run(orchestrator):
    task = orchestrator.create_task(
        title="Plan change",
        steps=[{"action": "echo", "parameters": {"message": "hello"}}],
    )
    result = orchestrator.execute(task.id)
    assert result.status == TaskStatus.SUCCEEDED
    assert result.steps[0].result["planned"] is True


def test_live_task_requires_confirmation(orchestrator):
    with pytest.raises(TaskOrchestrationError):
        orchestrator.create_task(
            title="Unsafe",
            steps=[{"action": "echo"}],
            dry_run=False,
            confirmed=False,
        )


def test_live_task_executes_registered_action(orchestrator):
    calls = []

    def action(parameters):
        calls.append(parameters)
        return {"ok": True}

    orchestrator.register_action("custom", action)
    task = orchestrator.create_task(
        title="Live task",
        steps=[{"action": "custom", "parameters": {"x": 1}}],
        dry_run=False,
        confirmed=True,
    )
    result = orchestrator.execute(task.id)
    assert result.status == TaskStatus.SUCCEEDED
    assert calls == [{"x": 1}]
    assert result.steps[0].result == {"ok": True}


def test_stop_on_error_persists_failure(orchestrator):
    task = orchestrator.create_task(
        title="Failing task",
        steps=[
            {
                "action": "assert",
                "parameters": {"condition": False, "message": "nope"},
            },
            {"action": "echo", "parameters": {"message": "never"}},
        ],
        dry_run=False,
        confirmed=True,
    )
    result = orchestrator.execute(task.id)
    assert result.status == TaskStatus.FAILED
    assert result.steps[0].status == StepStatus.FAILED
    assert result.steps[1].status == StepStatus.PENDING
    assert result.error == "nope"


def test_execution_is_restart_safe(orchestrator, tmp_path):
    task = orchestrator.create_task(
        title="Persistent",
        steps=[{"action": "echo", "parameters": {"message": "stored"}}],
    )
    reloaded = ChangeTaskOrchestrator(JsonTaskStore(tmp_path / "tasks"))
    found = reloaded.get(task.id)
    assert found.title == "Persistent"
    assert found.status == TaskStatus.PLANNED


def test_successful_task_is_idempotent(orchestrator):
    task = orchestrator.create_task(
        title="Idempotent",
        steps=[
            {
                "action": "echo",
                "parameters": {"message": "once"},
                "idempotency_key": "echo-once",
            }
        ],
    )
    first = orchestrator.execute(task.id)
    second = orchestrator.execute(task.id)
    assert first.status == TaskStatus.SUCCEEDED
    assert second.status == TaskStatus.SUCCEEDED
    assert len(second.history) == len(first.history)


def test_dry_run_rollback_marks_steps(orchestrator):
    task = orchestrator.create_task(
        title="Rollback",
        steps=[{"action": "echo", "parameters": {"message": "test"}}],
    )
    orchestrator.execute(task.id)
    result = orchestrator.rollback(task.id)
    assert result.status == TaskStatus.ROLLED_BACK
    assert result.steps[0].status == StepStatus.ROLLED_BACK


def test_cancel_planned_task(orchestrator):
    task = orchestrator.create_task(
        title="Cancel",
        steps=[{"action": "echo"}],
    )
    result = orchestrator.cancel(task.id)
    assert result.status == TaskStatus.CANCELLED
PY
ok "Orchestration regression tests installed"

step "Running compile checks"
cd "$BACKEND"
"$PYTHON_BIN" -m compileall -q app tests
ok "Python compile checks passed"

step "Running Milestone 21.9 regression suite"
tests=(tests/test_change_task_orchestration.py)
for candidate in \
  tests/test_github_workflow_observability.py \
  tests/test_github_pull_request_gates.py \
  tests/test_github_write_safety.py \
  tests/test_github_lazy_lifecycle.py \
  tests/test_github_runtime_token_resolution.py
do
  [[ -f "$candidate" ]] && tests+=("$candidate")
done
"$PYTHON_BIN" -m pytest -q "${tests[@]}"
ok "Milestone 21.9 regression suite passed"

step "Verifying credential-free OpenAPI"
ODIN_GITHUB_TOKEN="" "$PYTHON_BIN" - <<'PY'
from app.main import app

paths = app.openapi()["paths"]
required = {
    "/change-tasks",
    "/change-tasks/actions",
    "/change-tasks/{task_id}",
    "/change-tasks/{task_id}/execute",
    "/change-tasks/{task_id}/cancel",
    "/change-tasks/{task_id}/rollback",
}
missing = required - set(paths)
assert not missing, missing
assert "post" in paths["/change-tasks"]
assert "post" in paths["/change-tasks/{task_id}/execute"]
print(f"OpenAPI generated with {len(paths)} paths")
PY
ok "OpenAPI verification passed"

step "Checking autonomous execution invariants"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

service = Path("app/services/change_tasks.py").read_text()
api = Path("app/api/change_tasks.py").read_text()
main = Path("app/main.py").read_text()

assert "class ChangeTaskOrchestrator" in service
assert "class JsonTaskStore" in service
assert "TaskStatus" in service
assert "StepStatus" in service
assert "idempotency_key" in service
assert "def rollback(" in service
assert "dry_run: bool = True" in service
assert "confirmed: bool = False" in service
assert "/{task_id}/execute" in api
assert "/{task_id}/rollback" in api
assert "include_router(change_tasks_router)" in main
print("Autonomous execution invariants verified")
PY
ok "Autonomous execution invariants passed"

trap - ERR
printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\nBackup:       %s\n\n' "$CHECKS" "$BACKUP_DIR"
printf 'Installed:\n'
printf '  • Persistent autonomous change-task plans\n'
printf '  • Multi-step sequential execution\n'
printf '  • Dry-run execution by default\n'
printf '  • Explicit confirmation for live tasks\n'
printf '  • Idempotency-key protection\n'
printf '  • Restart-safe JSON task persistence\n'
printf '  • Task and step execution history\n'
printf '  • Stop-on-error controls\n'
printf '  • Cancellation and reverse-order rollback\n'
printf '  • Extensible action registry\n'
printf '  • REST task orchestration API\n'
printf '  • Compile, OpenAPI, and regression validation\n'
printf '  • Automatic backup, rollback, and rerun safety\n\n'
printf 'Next chunk: Milestone 22.0 — agent-driven GitHub change plans.\n'
