from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.execution.models import (
    ApprovalStatus,
    AttemptStatus,
    ExecutionApproval,
    ExecutionAttempt,
    ExecutionLimits,
    ExecutionRun,
    ExecutionStep,
    QueueClaim,
    RunStatus,
    StepStatus,
    utc_now,
)


class ExecutionStoreError(RuntimeError):
    pass


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _load(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class ExecutionStore:
    """SQLite authority for execution state and the leased work queue."""

    def __init__(self, database_path: str | Path = ".odin/executions.db"):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_lock = threading.Lock()
        self.initialize()

    @contextmanager
    def connect(self, *, begin_mode: str = "DEFERRED") -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        if begin_mode not in {"DEFERRED", "IMMEDIATE"}:
            raise ValueError("Unsupported SQLite transaction mode")
        db.execute(f"BEGIN {begin_mode}")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self._initialize_lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_runs (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    repository_id INTEGER,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    limits_json TEXT NOT NULL DEFAULT '{}',
                    current_step_id TEXT,
                    error TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS execution_steps (
                    id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    depends_on_json TEXT NOT NULL DEFAULT '[]',
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    PRIMARY KEY (run_id, id),
                    FOREIGN KEY (run_id) REFERENCES execution_runs(id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_step_idempotency
                    ON execution_steps(run_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL;
                CREATE TABLE IF NOT EXISTS execution_attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    worker_id TEXT,
                    result_json TEXT,
                    error TEXT,
                    retryable INTEGER,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(run_id, step_id, number),
                    FOREIGN KEY (run_id, step_id)
                        REFERENCES execution_steps(run_id, id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS execution_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    available_at TEXT NOT NULL,
                    claimed_by TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, step_id),
                    FOREIGN KEY (run_id, step_id)
                        REFERENCES execution_steps(run_id, id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS execution_approvals (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    decided_by TEXT,
                    reason TEXT,
                    FOREIGN KEY (run_id, step_id)
                        REFERENCES execution_steps(run_id, id) ON DELETE CASCADE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_execution_approval
                    ON execution_approvals(run_id, step_id)
                    WHERE status = 'pending';
                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES execution_runs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS execution_artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    uri TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES execution_runs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS execution_operation_receipts (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    worker_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    PRIMARY KEY (run_id, idempotency_key),
                    FOREIGN KEY (run_id, step_id)
                        REFERENCES execution_steps(run_id, id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_execution_runs_status
                    ON execution_runs(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_queue_available
                    ON execution_queue(available_at, priority, id);
                CREATE INDEX IF NOT EXISTS idx_execution_events_run
                    ON execution_events(run_id, id);
                """
            )

    def create_run(self, run: ExecutionRun, steps: list[ExecutionStep]) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO execution_runs VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id, run.goal, run.status.value, run.repository_id,
                    _dump(run.context), _dump(run.metadata), _dump(asdict(run.limits)),
                    run.current_step_id, run.error, run.created_by, run.created_at,
                    run.updated_at, run.started_at, run.completed_at, run.cancelled_at,
                ),
            )
            for step in steps:
                self._insert_step(db, step)

    @staticmethod
    def _insert_step(db: sqlite3.Connection, step: ExecutionStep) -> None:
        db.execute(
            """INSERT INTO execution_steps VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                step.id, step.run_id, step.position, step.kind,
                _dump(step.parameters), _dump(step.depends_on),
                int(step.requires_approval), step.idempotency_key,
                step.status.value, step.attempt_count,
                None if step.result is None else _dump(step.result), step.error,
                step.created_at, step.updated_at, step.started_at, step.completed_at,
            ),
        )

    @staticmethod
    def _run(row: sqlite3.Row) -> ExecutionRun:
        limits = ExecutionLimits(**_load(row["limits_json"], {}))
        return ExecutionRun(
            id=row["id"], goal=row["goal"], status=RunStatus(row["status"]),
            repository_id=row["repository_id"],
            context=_load(row["context_json"], {}),
            metadata=_load(row["metadata_json"], {}), limits=limits,
            current_step_id=row["current_step_id"], error=row["error"],
            created_by=row["created_by"], created_at=row["created_at"],
            updated_at=row["updated_at"], started_at=row["started_at"],
            completed_at=row["completed_at"], cancelled_at=row["cancelled_at"],
        )

    @staticmethod
    def _step(row: sqlite3.Row) -> ExecutionStep:
        return ExecutionStep(
            id=row["id"], run_id=row["run_id"], position=row["position"],
            kind=row["kind"], parameters=_load(row["parameters_json"], {}),
            depends_on=_load(row["depends_on_json"], []),
            requires_approval=bool(row["requires_approval"]),
            idempotency_key=row["idempotency_key"],
            status=StepStatus(row["status"]), attempt_count=row["attempt_count"],
            result=_load(row["result_json"], None), error=row["error"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            started_at=row["started_at"], completed_at=row["completed_at"],
        )

    def get_run(self, run_id: str) -> ExecutionRun:
        # Reserve the writer before selecting so concurrent workers cannot both
        # observe the same unclaimed row.
        with self.connect(begin_mode="IMMEDIATE") as db:
            row = db.execute(
                "SELECT * FROM execution_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ExecutionStoreError(f"Execution run not found: {run_id}")
        return self._run(row)

    def list_runs(self, limit: int = 100) -> list[ExecutionRun]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM execution_runs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._run(row) for row in rows]

    def list_steps(self, run_id: str) -> list[ExecutionStep]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM execution_steps WHERE run_id = ? ORDER BY position",
                (run_id,),
            ).fetchall()
        return [self._step(row) for row in rows]

    def get_step(self, run_id: str, step_id: str) -> ExecutionStep:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM execution_steps WHERE run_id = ? AND id = ?",
                (run_id, step_id),
            ).fetchone()
        if row is None:
            raise ExecutionStoreError(f"Execution step not found: {step_id}")
        return self._step(row)

    def update_run(self, run: ExecutionRun) -> None:
        run.updated_at = utc_now()
        with self.connect() as db:
            db.execute(
                """UPDATE execution_runs SET status=?, current_step_id=?, error=?,
                metadata_json=?, updated_at=?, started_at=?, completed_at=?,
                cancelled_at=? WHERE id=?""",
                (
                    run.status.value, run.current_step_id, run.error,
                    _dump(run.metadata), run.updated_at, run.started_at,
                    run.completed_at, run.cancelled_at, run.id,
                ),
            )

    def update_step(self, step: ExecutionStep) -> None:
        step.updated_at = utc_now()
        with self.connect() as db:
            db.execute(
                """UPDATE execution_steps SET status=?, attempt_count=?, result_json=?,
                error=?, updated_at=?, started_at=?, completed_at=?
                WHERE run_id=? AND id=?""",
                (
                    step.status.value, step.attempt_count,
                    None if step.result is None else _dump(step.result),
                    step.error, step.updated_at, step.started_at, step.completed_at,
                    step.run_id, step.id,
                ),
            )

    def enqueue(
        self,
        run_id: str,
        step_id: str,
        *,
        priority: int = 100,
        available_at: str | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO execution_queue
                (run_id, step_id, priority, available_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_id) DO UPDATE SET
                priority=excluded.priority, available_at=excluded.available_at,
                claimed_by=NULL, lease_expires_at=NULL""",
                (run_id, step_id, priority, available_at or now, now),
            )

    def claim_next(self, worker_id: str, lease_seconds: int = 30) -> QueueClaim | None:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        lease = (now + timedelta(seconds=lease_seconds)).isoformat()
        # Reserve the writer before selecting so concurrent workers cannot both
        # observe the same unclaimed row.
        with self.connect(begin_mode="IMMEDIATE") as db:
            row = db.execute(
                """SELECT q.* FROM execution_queue q
                JOIN execution_runs r ON r.id=q.run_id
                WHERE q.available_at <= ?
                  AND (q.claimed_by IS NULL OR q.lease_expires_at <= ?)
                  AND r.status NOT IN ('cancelled','failed','succeeded')
                ORDER BY q.priority ASC, q.available_at ASC, q.id ASC LIMIT 1""",
                (now_iso, now_iso),
            ).fetchone()
            if row is None:
                return None
            changed = db.execute(
                """UPDATE execution_queue SET claimed_by=?, lease_expires_at=?
                WHERE id=? AND (claimed_by IS NULL OR lease_expires_at <= ?)""",
                (worker_id, lease, row["id"], now_iso),
            ).rowcount
            if changed != 1:
                return None
        return QueueClaim(
            id=row["id"], run_id=row["run_id"], step_id=row["step_id"],
            worker_id=worker_id, lease_expires_at=lease,
        )

    def claim_is_active(self, claim: QueueClaim) -> bool:
        now = utc_now()
        with self.connect() as db:
            row = db.execute(
                """SELECT 1 FROM execution_queue q
                JOIN execution_runs r ON r.id=q.run_id
                WHERE q.id=? AND q.claimed_by=? AND q.lease_expires_at>?
                  AND r.status NOT IN ('cancelled','failed','succeeded')""",
                (claim.id, claim.worker_id, now),
            ).fetchone()
        return row is not None

    def heartbeat(self, claim: QueueClaim, lease_seconds: int = 30) -> bool:
        lease = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        with self.connect() as db:
            changed = db.execute(
                """UPDATE execution_queue SET lease_expires_at=?
                WHERE id=? AND claimed_by=?""",
                (lease, claim.id, claim.worker_id),
            ).rowcount
        claim.lease_expires_at = lease
        return changed == 1

    def complete_success(
        self, claim: QueueClaim, attempt: ExecutionAttempt, result: Any
    ) -> bool:
        """Commit a result only while this worker still owns a live claim."""
        now = utc_now()
        with self.connect(begin_mode="IMMEDIATE") as db:
            owned = db.execute(
                """SELECT 1 FROM execution_queue q
                JOIN execution_runs r ON r.id=q.run_id
                WHERE q.id=? AND q.claimed_by=? AND q.lease_expires_at>?
                  AND r.status NOT IN ('cancelled','failed','succeeded')""",
                (claim.id, claim.worker_id, now),
            ).fetchone()
            if owned is None:
                status = db.execute(
                    "SELECT status FROM execution_runs WHERE id=?", (claim.run_id,)
                ).fetchone()
                attempt_status = (
                    AttemptStatus.CANCELLED.value
                    if status and status["status"] == RunStatus.CANCELLED.value
                    else AttemptStatus.INTERRUPTED.value
                )
                db.execute(
                    """UPDATE execution_attempts SET status=?, error=?,
                    completed_at=? WHERE id=? AND status='running'""",
                    (attempt_status, "claim lost before completion", now, attempt.id),
                )
                return False
            db.execute(
                """UPDATE execution_attempts SET status='succeeded',
                result_json=?, completed_at=? WHERE id=? AND status='running'""",
                (_dump(result), now, attempt.id),
            )
            db.execute(
                """UPDATE execution_steps SET status='succeeded', result_json=?,
                error=NULL, updated_at=?, completed_at=?
                WHERE run_id=? AND id=? AND status='running'""",
                (_dump(result), now, now, claim.run_id, claim.step_id),
            )
            db.execute(
                "DELETE FROM execution_queue WHERE id=? AND claimed_by=?",
                (claim.id, claim.worker_id),
            )
        attempt.status = AttemptStatus.SUCCEEDED
        attempt.result = result
        attempt.completed_at = now
        return True

    def complete_failure(
        self,
        claim: QueueClaim,
        attempt: ExecutionAttempt,
        *,
        error: str,
        retryable: bool,
        available_at: str | None = None,
    ) -> str:
        """Fence failure/retry persistence against cancellation and lease loss."""
        now = utc_now()
        with self.connect(begin_mode="IMMEDIATE") as db:
            run_row = db.execute(
                "SELECT status FROM execution_runs WHERE id=?", (claim.run_id,)
            ).fetchone()
            owned = db.execute(
                """SELECT 1 FROM execution_queue
                WHERE id=? AND claimed_by=? AND lease_expires_at>?""",
                (claim.id, claim.worker_id, now),
            ).fetchone()
            if (
                owned is None
                or run_row is None
                or run_row["status"] in {"cancelled", "failed", "succeeded"}
            ):
                lost_status = (
                    AttemptStatus.CANCELLED.value
                    if run_row and run_row["status"] == "cancelled"
                    else AttemptStatus.INTERRUPTED.value
                )
                db.execute(
                    """UPDATE execution_attempts SET status=?, error=?,
                    completed_at=? WHERE id=? AND status='running'""",
                    (lost_status, "claim lost before failure commit", now, attempt.id),
                )
                return "lost"
            db.execute(
                """UPDATE execution_attempts SET status='failed', error=?,
                retryable=?, completed_at=? WHERE id=? AND status='running'""",
                (error, int(retryable), now, attempt.id),
            )
            if retryable:
                db.execute(
                    """UPDATE execution_steps SET status='retry_scheduled',
                    error=?, updated_at=? WHERE run_id=? AND id=? AND status='running'""",
                    (error, now, claim.run_id, claim.step_id),
                )
                db.execute(
                    """UPDATE execution_runs SET status='retry_scheduled',
                    updated_at=? WHERE id=?""", (now, claim.run_id)
                )
                db.execute(
                    """UPDATE execution_queue SET available_at=?, claimed_by=NULL,
                    lease_expires_at=NULL WHERE id=? AND claimed_by=?""",
                    (available_at or now, claim.id, claim.worker_id),
                )
                return "retry"
            db.execute(
                """UPDATE execution_steps SET status='failed', error=?,
                updated_at=?, completed_at=? WHERE run_id=? AND id=?
                AND status='running'""",
                (error, now, now, claim.run_id, claim.step_id),
            )
            db.execute(
                """UPDATE execution_runs SET status='failed', error=?,
                updated_at=?, completed_at=? WHERE id=?""",
                (error, now, now, claim.run_id),
            )
            db.execute(
                "DELETE FROM execution_queue WHERE id=? AND claimed_by=?",
                (claim.id, claim.worker_id),
            )
            return "failed"

    def begin_operation(
        self, step: ExecutionStep, worker_id: str
    ) -> tuple[str, Any]:
        """Return new, completed, or indeterminate for an idempotent operation."""
        if not step.idempotency_key:
            return ("new", None)
        now = utc_now()
        with self.connect(begin_mode="IMMEDIATE") as db:
            row = db.execute(
                """SELECT * FROM execution_operation_receipts
                WHERE run_id=? AND idempotency_key=?""",
                (step.run_id, step.idempotency_key),
            ).fetchone()
            if row is None:
                db.execute(
                    """INSERT INTO execution_operation_receipts
                    (run_id,step_id,idempotency_key,status,worker_id,started_at)
                    VALUES (?,?,?,?,?,?)""",
                    (
                        step.run_id, step.id, step.idempotency_key,
                        "running", worker_id, now,
                    ),
                )
                return ("new", None)
            if row["status"] == "completed":
                return ("completed", _load(row["result_json"], None))
            return ("indeterminate", None)

    def complete_operation(self, step: ExecutionStep, result: Any) -> None:
        if not step.idempotency_key:
            return
        with self.connect(begin_mode="IMMEDIATE") as db:
            db.execute(
                """UPDATE execution_operation_receipts SET status='completed',
                result_json=?, completed_at=? WHERE run_id=? AND idempotency_key=?
                AND status='running'""",
                (_dump(result), utc_now(), step.run_id, step.idempotency_key),
            )

    def release_claim(self, claim: QueueClaim, *, delete: bool = True) -> None:
        with self.connect() as db:
            if delete:
                db.execute(
                    "DELETE FROM execution_queue WHERE id=? AND claimed_by=?",
                    (claim.id, claim.worker_id),
                )
            else:
                db.execute(
                    """UPDATE execution_queue SET claimed_by=NULL, lease_expires_at=NULL
                    WHERE id=? AND claimed_by=?""",
                    (claim.id, claim.worker_id),
                )

    def begin_attempt(self, step: ExecutionStep, worker_id: str) -> ExecutionAttempt:
        attempt = ExecutionAttempt(
            id=uuid.uuid4().hex, run_id=step.run_id, step_id=step.id,
            number=step.attempt_count + 1, worker_id=worker_id,
        )
        with self.connect() as db:
            db.execute(
                """INSERT INTO execution_attempts
                (id,run_id,step_id,number,status,worker_id,started_at)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    attempt.id, attempt.run_id, attempt.step_id, attempt.number,
                    attempt.status.value, worker_id, attempt.started_at,
                ),
            )
        return attempt

    def finish_attempt(self, attempt: ExecutionAttempt) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE execution_attempts SET status=?, result_json=?, error=?,
                retryable=?, completed_at=? WHERE id=?""",
                (
                    attempt.status.value,
                    None if attempt.result is None else _dump(attempt.result),
                    attempt.error,
                    None if attempt.retryable is None else int(attempt.retryable),
                    attempt.completed_at, attempt.id,
                ),
            )

    def list_attempts(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM execution_attempts WHERE run_id=?
                ORDER BY started_at, number""", (run_id,)
            ).fetchall()
        return [
            {
                **dict(row),
                "result": _load(row["result_json"], None),
                "retryable": (
                    None if row["retryable"] is None else bool(row["retryable"])
                ),
            }
            for row in rows
        ]

    def request_approval(self, run_id: str, step_id: str) -> ExecutionApproval:
        approval = ExecutionApproval(
            id=uuid.uuid4().hex, run_id=run_id, step_id=step_id
        )
        with self.connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO execution_approvals
                (id,run_id,step_id,status,requested_at) VALUES (?,?,?,?,?)""",
                (
                    approval.id, run_id, step_id, approval.status.value,
                    approval.requested_at,
                ),
            )
            row = db.execute(
                """SELECT * FROM execution_approvals
                WHERE run_id=? AND step_id=? AND status='pending'""",
                (run_id, step_id),
            ).fetchone()
        return self._approval(row)

    @staticmethod
    def _approval(row: sqlite3.Row) -> ExecutionApproval:
        return ExecutionApproval(
            id=row["id"], run_id=row["run_id"], step_id=row["step_id"],
            status=ApprovalStatus(row["status"]),
            requested_at=row["requested_at"], decided_at=row["decided_at"],
            decided_by=row["decided_by"], reason=row["reason"],
        )

    def pending_approval(self, run_id: str) -> ExecutionApproval | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT * FROM execution_approvals
                WHERE run_id=? AND status='pending' ORDER BY requested_at LIMIT 1""",
                (run_id,),
            ).fetchone()
        return None if row is None else self._approval(row)

    def decide_approval(
        self, run_id: str, *, approved: bool, actor: str, reason: str | None
    ) -> ExecutionApproval:
        with self.connect() as db:
            row = db.execute(
                """SELECT * FROM execution_approvals
                WHERE run_id=? AND status='pending' ORDER BY requested_at LIMIT 1""",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ExecutionStoreError("No pending approval for execution")
            status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            decided_at = utc_now()
            db.execute(
                """UPDATE execution_approvals SET status=?, decided_at=?,
                decided_by=?, reason=? WHERE id=?""",
                (status.value, decided_at, actor, reason, row["id"]),
            )
            updated = db.execute(
                "SELECT * FROM execution_approvals WHERE id=?", (row["id"],)
            ).fetchone()
        return self._approval(updated)

    def approval_for_step(self, run_id: str, step_id: str) -> ApprovalStatus | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT status FROM execution_approvals
                WHERE run_id=? AND step_id=? ORDER BY requested_at DESC LIMIT 1""",
                (run_id, step_id),
            ).fetchone()
        return None if row is None else ApprovalStatus(row["status"])

    def append_event(
        self, run_id: str, event_type: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        created_at = utc_now()
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO execution_events
                (run_id,event_type,payload_json,created_at) VALUES (?,?,?,?)""",
                (run_id, event_type, _dump(payload or {}), created_at),
            )
        return {
            "id": cursor.lastrowid, "run_id": run_id, "type": event_type,
            "payload": payload or {}, "created_at": created_at,
        }

    def list_events(self, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM execution_events WHERE run_id=?
                ORDER BY id ASC LIMIT ?""", (run_id, max(1, min(limit, 1000)))
            ).fetchall()
        return [
            {
                "id": row["id"], "run_id": row["run_id"],
                "type": row["event_type"],
                "payload": _load(row["payload_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def recover_expired(self) -> list[tuple[str, str]]:
        now = utc_now()
        recovered: list[tuple[str, str]] = []
        with self.connect() as db:
            rows = db.execute(
                """SELECT run_id,step_id FROM execution_queue
                WHERE claimed_by IS NOT NULL AND lease_expires_at <= ?""",
                (now,),
            ).fetchall()
            for row in rows:
                recovered.append((row["run_id"], row["step_id"]))
                db.execute(
                    """UPDATE execution_steps SET status='interrupted', updated_at=?
                    WHERE run_id=? AND id=? AND status='running'""",
                    (now, row["run_id"], row["step_id"]),
                )
                db.execute(
                    """UPDATE execution_runs SET status='interrupted', updated_at=?
                    WHERE id=? AND status='running'""",
                    (now, row["run_id"]),
                )
            db.execute(
                """UPDATE execution_queue SET claimed_by=NULL, lease_expires_at=NULL
                WHERE claimed_by IS NOT NULL AND lease_expires_at <= ?""", (now,)
            )
            db.execute(
                """UPDATE execution_attempts SET status='interrupted',
                error='worker lease expired', retryable=1, completed_at=?
                WHERE status='running' AND EXISTS (
                    SELECT 1 FROM execution_queue q
                    WHERE q.run_id=execution_attempts.run_id
                      AND q.step_id=execution_attempts.step_id
                      AND q.claimed_by IS NULL)""", (now,)
            )
        return recovered

    def queue_depth(self) -> int:
        with self.connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM execution_queue").fetchone()[0])
