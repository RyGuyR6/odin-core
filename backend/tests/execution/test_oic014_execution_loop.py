from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.execution.handlers import HandlerRegistry
from app.execution.models import ExecutionLimits, RunStatus, StepStatus
from app.execution.persistence import ExecutionStore
from app.execution.service import ExecutionService


@pytest.fixture
def service(tmp_path: Path) -> ExecutionService:
    return ExecutionService(ExecutionStore(tmp_path / "executions.db"))


def drain(service: ExecutionService):
    result = None
    while (current := service.run_next("test-worker")) is not None:
        result = current
    return result


def test_plan_executes_dependencies_and_persists_attempts(service):
    created = service.create(
        goal="Execute a durable plan",
        steps=[
            {"id": "analyze", "kind": "record"},
            {"id": "report", "kind": "echo", "depends_on": ["analyze"]},
        ],
    )
    completed = drain(service)
    assert created["status"] == "queued"
    assert completed["status"] == "succeeded"
    assert completed["progress"]["percent"] == 100.0
    assert [item["number"] for item in service.attempts_for(created["id"])] == [1, 1]


def test_approval_pauses_and_resumes_exact_step(service):
    run = service.create(
        goal="Require a human checkpoint",
        steps=[{"id": "mutate", "kind": "record", "requires_approval": True}],
    )
    paused = service.run_next("worker")
    assert paused["status"] == "awaiting_approval"
    assert paused["pending_approval"]["step_id"] == "mutate"
    assert service.attempts_for(run["id"]) == []
    service.approve(run["id"], actor="reviewer", reason="safe")
    assert service.run_next("worker")["status"] == "succeeded"


def test_rejected_approval_never_invokes_handler(tmp_path):
    calls = []
    handlers = HandlerRegistry()
    handlers.register("mutation", lambda step, run: calls.append(step.id))
    service = ExecutionService(
        ExecutionStore(tmp_path / "executions.db"), handlers=handlers
    )
    run = service.create(
        goal="Reject mutation",
        steps=[{"kind": "mutation", "requires_approval": True}],
    )
    service.run_next("worker")
    rejected = service.reject(run["id"], actor="reviewer", reason="not approved")
    assert rejected["status"] == "cancelled"
    assert calls == []


def test_retry_is_bounded_and_attempts_are_independent(tmp_path):
    calls = []

    def unstable(step, run):
        calls.append(step.id)
        raise RuntimeError("temporary")

    handlers = HandlerRegistry()
    handlers.register("unstable", unstable)
    service = ExecutionService(
        ExecutionStore(tmp_path / "executions.db"), handlers=handlers
    )
    run = service.create(
        goal="Retry safely",
        steps=[{"kind": "unstable"}],
        limits=ExecutionLimits(max_attempts=2),
    )
    assert service.run_next("worker")["status"] == "retry_scheduled"
    with service.store.connect() as db:
        db.execute(
            "UPDATE execution_queue SET available_at=? WHERE run_id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), run["id"]),
        )
    assert service.run_next("worker")["status"] == "failed"
    assert [item["number"] for item in service.attempts_for(run["id"])] == [1, 2]
    assert len(calls) == 2


def test_atomic_claim_allows_only_one_worker(service):
    service.create(goal="Claim once", steps=[{"kind": "echo"}])
    assert service.store.claim_next("worker-one") is not None
    assert service.store.claim_next("worker-two") is None


def test_expired_lease_is_recovered_and_resumed(service):
    run = service.create(goal="Recover", steps=[{"kind": "echo"}])
    claim = service.store.claim_next("dead-worker")
    step = service.store.get_step(run["id"], claim.step_id)
    step.status = StepStatus.RUNNING
    service.store.update_step(step)
    current = service.store.get_run(run["id"])
    current.status = RunStatus.RUNNING
    service.store.update_run(current)
    with service.store.connect() as db:
        db.execute(
            "UPDATE execution_queue SET lease_expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), claim.id),
        )
    assert service.controller.recover() == [(run["id"], claim.step_id)]
    assert service.run_next("new-worker")["status"] == "succeeded"


def test_cancel_is_idempotent_and_prevents_claim(service):
    run = service.create(goal="Cancel", steps=[{"kind": "echo"}])
    assert service.cancel(run["id"], actor="owner")["status"] == "cancelled"
    assert service.cancel(run["id"], actor="owner")["status"] == "cancelled"
    assert service.store.claim_next("worker") is None


def test_unknown_dependencies_are_rejected(service):
    with pytest.raises(ValueError, match="unknown dependencies"):
        service.create(
            goal="Invalid",
            steps=[{"id": "one", "kind": "echo", "depends_on": ["missing"]}],
        )


def test_dependency_cycles_are_rejected(service):
    with pytest.raises(ValueError, match="dependency cycle"):
        service.create(
            goal="Cycle",
            steps=[
                {"id": "one", "kind": "echo", "depends_on": ["two"]},
                {"id": "two", "kind": "echo", "depends_on": ["one"]},
            ],
        )


def test_state_survives_service_restart(tmp_path):
    path = tmp_path / "executions.db"
    first = ExecutionService(ExecutionStore(path))
    run = first.create(goal="Restart", steps=[{"kind": "echo"}])
    restarted = ExecutionService(ExecutionStore(path))
    assert restarted.get(run["id"])["status"] == "queued"
    assert restarted.run_next("restarted-worker")["status"] == "succeeded"
