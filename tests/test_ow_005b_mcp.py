from __future__ import annotations

from pathlib import Path

import pytest

from odin_mcp.core.mcp_models import TaskRecord
from odin_mcp.core.mcp_store import (
    SQLiteTaskStore,
    TaskConflictError,
    TaskNotFoundError,
)
from odin_mcp.core.runtime_log import RuntimeLog


def test_task_lifecycle(tmp_path: Path) -> None:
    store = SQLiteTaskStore(tmp_path / "odin.db")
    task = TaskRecord.create(
        title="Verify MCP",
        priority="high",
        labels=["ow-005b", "mcp"],
    )

    created = store.create(task)
    assert created.status == "pending"
    assert store.get(created.id).title == "Verify MCP"

    listed = store.list(priority="high")
    assert [item.id for item in listed] == [created.id]

    cancelled = store.cancel(created.id)
    assert cancelled.status == "cancelled"

    with pytest.raises(TaskConflictError):
        store.cancel(created.id)


def test_missing_task(tmp_path: Path) -> None:
    store = SQLiteTaskStore(tmp_path / "odin.db")
    with pytest.raises(TaskNotFoundError):
        store.get("task_missing")


def test_runtime_log(tmp_path: Path) -> None:
    runtime_log = RuntimeLog(tmp_path / "runtime.jsonl")
    runtime_log.write("test.event", data={"value": 1})
    runtime_log.write("other.event", level="warning")

    entries = runtime_log.read(limit=10)
    assert len(entries) == 2
    assert entries[0]["event"] == "other.event"

    filtered = runtime_log.read(limit=10, event="test.event")
    assert len(filtered) == 1
    assert filtered[0]["data"]["value"] == 1
