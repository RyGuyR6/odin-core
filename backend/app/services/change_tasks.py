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
