from __future__ import annotations

from pathlib import Path

import pytest

from odin_mcp.config import MCPSettings
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


def test_mcp_settings_prefer_canonical_memory_db(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "backend" / "data").mkdir(parents=True)
    data_dir = tmp_path / ".odin"
    shared_path = (tmp_path / "memory.db").resolve()
    legacy_path = (tmp_path / "legacy-odin.db").resolve()

    monkeypatch.setenv("ODIN_ROOT", str(repo_root))
    monkeypatch.setenv("ODIN_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ODIN_MEMORY_DB", str(shared_path))
    monkeypatch.setenv("ODIN_DATABASE_PATH", str(legacy_path))

    settings = MCPSettings.from_environment()

    assert settings.database_path == shared_path


def test_mcp_settings_share_backend_memory_db_when_available(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    backend_data_dir = repo_root / "backend" / "data"
    backend_data_dir.mkdir(parents=True)
    data_dir = repo_root / ".odin"

    monkeypatch.delenv("ODIN_MEMORY_DB", raising=False)
    monkeypatch.delenv("ODIN_DATABASE_PATH", raising=False)
    monkeypatch.setenv("ODIN_ROOT", str(repo_root))
    monkeypatch.setenv("ODIN_DATA_DIR", str(data_dir))

    settings = MCPSettings.from_environment()

    assert settings.database_path == (backend_data_dir / "memory.db").resolve()


def test_mcp_settings_keep_local_database_without_backend_memory_db(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    data_dir = tmp_path / ".odin"

    monkeypatch.delenv("ODIN_MEMORY_DB", raising=False)
    monkeypatch.delenv("ODIN_DATABASE_PATH", raising=False)
    monkeypatch.setenv("ODIN_ROOT", str(repo_root))
    monkeypatch.setenv("ODIN_DATA_DIR", str(data_dir))

    settings = MCPSettings.from_environment()

    assert settings.database_path == (data_dir / "odin.db").resolve()
