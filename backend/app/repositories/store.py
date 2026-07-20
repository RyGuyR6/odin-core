from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from .models import WorkspaceRecord, WorkspaceState, utcnow

class RepositoryStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL UNIQUE,
                    repository_url TEXT,
                    default_branch TEXT,
                    current_branch TEXT,
                    head_sha TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS repository_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT,
                    event_type TEXT NOT NULL,
                    actor_id TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_repository_events_workspace
                    ON repository_events(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS file_index (
                    workspace_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    language TEXT,
                    binary INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(workspace_id, path)
                );
            """)

    @staticmethod
    def _workspace(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            id=row["id"], name=row["name"], path=row["path"],
            repository_url=row["repository_url"], default_branch=row["default_branch"],
            current_branch=row["current_branch"], head_sha=row["head_sha"],
            state=WorkspaceState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def save_workspace(self, record: WorkspaceRecord) -> None:
        record.updated_at = utcnow()
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO workspaces(
                    id,name,path,repository_url,default_branch,current_branch,head_sha,
                    state,created_at,updated_at,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,path=excluded.path,repository_url=excluded.repository_url,
                    default_branch=excluded.default_branch,current_branch=excluded.current_branch,
                    head_sha=excluded.head_sha,state=excluded.state,updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
            """, (
                record.id, record.name, record.path, record.repository_url,
                record.default_branch, record.current_branch, record.head_sha,
                record.state.value, record.created_at.isoformat(), record.updated_at.isoformat(),
                json.dumps(record.metadata, sort_keys=True),
            ))

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        return self._workspace(row) if row else None

    def get_workspace_by_name(self, name: str) -> WorkspaceRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE name=?", (name,)).fetchone()
        return self._workspace(row) if row else None

    def list_workspaces(self, include_deleted: bool = False) -> list[WorkspaceRecord]:
        query = "SELECT * FROM workspaces"
        params: tuple[Any, ...] = ()
        if not include_deleted:
            query += " WHERE state != ?"
            params = (WorkspaceState.deleted.value,)
        query += " ORDER BY updated_at DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._workspace(row) for row in rows]

    def delete_workspace(self, workspace_id: str, hard: bool = False) -> None:
        with self._lock, self._connect() as conn:
            if hard:
                conn.execute("DELETE FROM file_index WHERE workspace_id=?", (workspace_id,))
                conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
            else:
                conn.execute(
                    "UPDATE workspaces SET state=?,updated_at=? WHERE id=?",
                    (WorkspaceState.deleted.value, utcnow().isoformat(), workspace_id),
                )

    def record_event(self, workspace_id: str | None, event_type: str, actor_id: str | None = None, payload: dict | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO repository_events(workspace_id,event_type,actor_id,payload_json,created_at) VALUES(?,?,?,?,?)",
                (workspace_id, event_type, actor_id, json.dumps(payload or {}, sort_keys=True), utcnow().isoformat()),
            )

    def events(self, workspace_id: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM repository_events"
        params: list[Any] = []
        if workspace_id:
            query += " WHERE workspace_id=?"
            params.append(workspace_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{
            "id": row["id"], "workspace_id": row["workspace_id"],
            "event_type": row["event_type"], "actor_id": row["actor_id"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": row["created_at"],
        } for row in rows]

    def replace_index(self, workspace_id: str, entries: list[dict]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM file_index WHERE workspace_id=?", (workspace_id,))
            conn.executemany("""
                INSERT INTO file_index(workspace_id,path,size,modified_ns,sha256,kind,language,binary)
                VALUES(?,?,?,?,?,?,?,?)
            """, [
                (workspace_id, e["path"], e["size"], e["modified_ns"], e["sha256"],
                 e["kind"], e.get("language"), int(e.get("binary", False)))
                for e in entries
            ])

    def search_index(self, workspace_id: str, query: str, limit: int = 100) -> list[dict]:
        pattern = f"%{query}%"
        with self._lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT path,size,modified_ns,sha256,kind,language,binary
                FROM file_index
                WHERE workspace_id=? AND path LIKE ?
                ORDER BY path LIMIT ?
            """, (workspace_id, pattern, limit)).fetchall()
        return [dict(row) for row in rows]

    def index_count(self, workspace_id: str) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM file_index WHERE workspace_id=?", (workspace_id,)).fetchone()
        return int(row["count"])
