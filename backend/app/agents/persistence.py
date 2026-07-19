from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    prompt_template TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    temperature REAL,
                    max_tokens INTEGER,
                    timeout_seconds INTEGER,
                    retry_policy_json TEXT NOT NULL DEFAULT '{}',
                    permissions_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    output_json TEXT,
                    error TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    conversation_id TEXT,
                    session_id TEXT,
                    provider TEXT,
                    model TEXT,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'sequential',
                    steps_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    built_in INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    step_runs_json TEXT NOT NULL DEFAULT '[]',
                    output_json TEXT,
                    error TEXT,
                    conversation_id TEXT,
                    session_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runs_status
                    ON agent_runs(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_agent
                    ON agent_runs(agent_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
                    ON workflow_runs(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_events_run
                    ON agent_events(run_id, created_at);
                """
            )

    @staticmethod
    def dump_json(value) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)

    @staticmethod
    def load_json(value: str | None, fallback=None):
        if value is None:
            return {} if fallback is None else fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {} if fallback is None else fallback
