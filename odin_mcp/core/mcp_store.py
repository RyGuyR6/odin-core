"""SQLite persistence for the initial Odin MCP task tools."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
import json
import sqlite3

from odin_mcp.core.mcp_models import TaskRecord, utc_now
from odin_shared.sqlite_persistence import connect_sqlite


class TaskNotFoundError(LookupError):
    pass


class TaskConflictError(RuntimeError):
    pass


class SQLiteTaskStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = connect_sqlite(self.database_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS mcp_tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    labels_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_mcp_tasks_status
                    ON mcp_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_mcp_tasks_priority
                    ON mcp_tasks(priority);
                CREATE INDEX IF NOT EXISTS idx_mcp_tasks_created_at
                    ON mcp_tasks(created_at DESC);
                """
            )

    def create(self, task: TaskRecord) -> TaskRecord:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO mcp_tasks (
                    id, title, description, status, priority,
                    labels_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.description,
                    task.status,
                    task.priority,
                    json.dumps(task.labels),
                    json.dumps(task.metadata),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get(self, task_id: str) -> TaskRecord:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM mcp_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

        if row is None:
            raise TaskNotFoundError(f"Task '{task_id}' was not found.")
        return TaskRecord.from_row(row)

    def list(
        self,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        if offset < 0:
            raise ValueError("offset cannot be negative.")

        clauses: list[str] = []
        parameters: list[Any] = []

        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if priority:
            clauses.append("priority = ?")
            parameters.append(priority)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.extend([limit, offset])

        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM mcp_tasks
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()

        return [TaskRecord.from_row(row) for row in rows]

    def cancel(self, task_id: str) -> TaskRecord:
        current = self.get(task_id)
        if current.status in {"completed", "failed", "cancelled"}:
            raise TaskConflictError(
                f"Task '{task_id}' cannot be cancelled from status "
                f"'{current.status}'."
            )

        updated_at = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE mcp_tasks
                SET status = 'cancelled', updated_at = ?
                WHERE id = ?
                """,
                (updated_at, task_id),
            )

        return self.get(task_id)

    def counts(self) -> dict[str, int]:
        result = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }

        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM mcp_tasks
                GROUP BY status
                """
            ).fetchall()

        for row in rows:
            result[row["status"]] = row["count"]
            result["total"] += row["count"]
        return result
