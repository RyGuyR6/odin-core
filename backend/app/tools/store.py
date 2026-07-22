from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from .models import (
    ApprovalRequest, ApprovalStatus, ExecutionStatus, RiskLevel,
    ToolExecutionRecord,
)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ToolStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        self.initialize()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def initialize(self):
        with self._connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                status TEXT NOT NULL,
                risk TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                actor_id TEXT NOT NULL,
                agent_id TEXT,
                workspace_id TEXT NOT NULL,
                approval_id TEXT,
                idempotency_key TEXT UNIQUE,
                started_at TEXT,
                finished_at TEXT,
                elapsed_ms REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tool_exec_created ON tool_executions(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tool_exec_tool ON tool_executions(tool_name);
            CREATE INDEX IF NOT EXISTS idx_tool_exec_status ON tool_executions(status);
            CREATE TABLE IF NOT EXISTS tool_approvals (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL UNIQUE,
                tool_name TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                note TEXT,
                FOREIGN KEY(execution_id) REFERENCES tool_executions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tool_approval_status ON tool_approvals(status);
            CREATE TABLE IF NOT EXISTS tool_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(execution_id) REFERENCES tool_executions(id) ON DELETE CASCADE
            );
            """)

    def create_execution(self, record: ToolExecutionRecord, idempotency_key: str | None = None):
        with self._connect() as con:
            con.execute("""
            INSERT INTO tool_executions (
                id,tool_name,tool_version,status,risk,arguments_json,result_json,error,
                actor_id,agent_id,workspace_id,approval_id,idempotency_key,started_at,
                finished_at,elapsed_ms,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                record.id, record.tool_name, record.tool_version, record.status.value,
                record.risk.value, json.dumps(record.arguments), None, record.error,
                record.actor_id, record.agent_id, record.workspace_id, record.approval_id,
                idempotency_key, None, None, None, record.created_at.isoformat()
            ))

    def update_execution(self, execution_id: str, **fields):
        allowed = {"status","result","error","approval_id","started_at","finished_at","elapsed_ms"}
        updates, values = [], []
        for key, value in fields.items():
            if key not in allowed: continue
            col = "result_json" if key == "result" else key
            if key == "result": value = json.dumps(value, default=str)
            elif hasattr(value, "value"): value = value.value
            elif isinstance(value, datetime): value = value.isoformat()
            updates.append(f"{col}=?"); values.append(value)
        if not updates: return
        values.append(execution_id)
        with self._connect() as con:
            con.execute(f"UPDATE tool_executions SET {','.join(updates)} WHERE id=?", values)

    def get_execution(self, execution_id: str) -> ToolExecutionRecord | None:
        with self._connect() as con:
            row = con.execute("""
            SELECT e.*, a.status AS approval_status
            FROM tool_executions e
            LEFT JOIN tool_approvals a ON a.id = e.approval_id
            WHERE e.id=?
            """, (execution_id,)).fetchone()
        return self._execution_from_row(row) if row else None

    def get_by_idempotency(self, key: str) -> ToolExecutionRecord | None:
        with self._connect() as con:
            row = con.execute("""
            SELECT e.*, a.status AS approval_status
            FROM tool_executions e
            LEFT JOIN tool_approvals a ON a.id = e.approval_id
            WHERE e.idempotency_key=?
            """, (key,)).fetchone()
        return self._execution_from_row(row) if row else None

    def list_executions(self, limit=100, status: str | None=None, tool_name: str | None=None):
        sql = """
        SELECT e.*, a.status AS approval_status
        FROM tool_executions e
        LEFT JOIN tool_approvals a ON a.id = e.approval_id
        WHERE 1=1
        """
        args=[]
        if status: sql += " AND status=?"; args.append(status)
        if tool_name: sql += " AND tool_name=?"; args.append(tool_name)
        sql += " ORDER BY e.created_at DESC LIMIT ?"; args.append(limit)
        with self._connect() as con:
            rows=con.execute(sql,args).fetchall()
        return [self._execution_from_row(r) for r in rows]

    def create_approval(self, approval: ApprovalRequest):
        with self._connect() as con:
            con.execute("""
            INSERT INTO tool_approvals
            (id,execution_id,tool_name,actor_id,reason,status,expires_at,created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """, (
                approval.id,approval.execution_id,approval.tool_name,approval.actor_id,
                approval.reason,approval.status.value,approval.expires_at.isoformat(),
                approval.created_at.isoformat()
            ))

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        with self._connect() as con:
            row=con.execute("SELECT * FROM tool_approvals WHERE id=?",(approval_id,)).fetchone()
        if not row: return None
        return ApprovalRequest(
            id=row["id"],execution_id=row["execution_id"],tool_name=row["tool_name"],
            actor_id=row["actor_id"],reason=row["reason"],status=ApprovalStatus(row["status"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
            decided_by=row["decided_by"],
            note=row["note"],
        )

    def list_approvals(self, limit=100, status: str | None = None):
        sql = "SELECT * FROM tool_approvals WHERE 1=1"
        args: list[Any] = []
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        return [
            ApprovalRequest(
                id=row["id"],
                execution_id=row["execution_id"],
                tool_name=row["tool_name"],
                actor_id=row["actor_id"],
                reason=row["reason"],
                status=ApprovalStatus(row["status"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
                decided_by=row["decided_by"],
                note=row["note"],
            )
            for row in rows
        ]

    def decide_approval(self, approval_id: str, approved: bool, decided_by: str, note: str | None):
        status = ApprovalStatus.approved if approved else ApprovalStatus.denied
        with self._connect() as con:
            con.execute("""
            UPDATE tool_approvals SET status=?,decided_at=?,decided_by=?,note=? WHERE id=?
            """,(status.value,utcnow().isoformat(),decided_by,note,approval_id))

    def audit(self, event_type: str, payload: dict[str,Any], execution_id: str | None=None):
        with self._connect() as con:
            con.execute(
                "INSERT INTO tool_audit_events(execution_id,event_type,payload_json,created_at) VALUES (?,?,?,?)",
                (execution_id,event_type,json.dumps(payload,default=str),utcnow().isoformat())
            )

    def audit_events(self, limit=100):
        with self._connect() as con:
            rows=con.execute("SELECT * FROM tool_audit_events ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload_json"])} for r in rows]

    def execution_events(self, execution_id: str, limit=100):
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM tool_audit_events
                WHERE execution_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (execution_id, limit),
            ).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload_json"])} for r in rows]

    def telemetry(self):
        with self._connect() as con:
            rows=con.execute("SELECT status,COUNT(*) n FROM tool_executions GROUP BY status").fetchall()
            counts={r["status"]:r["n"] for r in rows}
            avg=con.execute("SELECT COALESCE(AVG(elapsed_ms),0) FROM tool_executions WHERE elapsed_ms IS NOT NULL").fetchone()[0]
        return counts, float(avg or 0)

    def _execution_from_row(self,row):
        return ToolExecutionRecord(
            id=row["id"],tool_name=row["tool_name"],tool_version=row["tool_version"],
            status=ExecutionStatus(row["status"]),risk=RiskLevel(row["risk"]),
            arguments=json.loads(row["arguments_json"]),result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],actor_id=row["actor_id"],agent_id=row["agent_id"],
            workspace_id=row["workspace_id"],approval_id=row["approval_id"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            elapsed_ms=row["elapsed_ms"],created_at=datetime.fromisoformat(row["created_at"]),
            approval_status=ApprovalStatus(row["approval_status"]) if row["approval_status"] else None,
        )
