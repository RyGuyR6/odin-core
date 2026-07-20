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
