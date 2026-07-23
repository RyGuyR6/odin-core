from __future__ import annotations

from pathlib import Path

from app.agents.config import get_agent_settings
from app.api.repositories import resolve_repository_database_path as resolve_api_repository_db
from app.conversations.config import get_conversation_settings
from app.memory.config import get_memory_settings
from app.repositories.config import get_repository_settings
from app.services.repository_intelligence import resolve_repository_database_path as resolve_intelligence_repository_db
from app.services.task_workspaces import TaskWorkspaceService
from app.storage.service import resolve_database_path
from app.tools.config import get_tool_settings


def _clear_database_env(monkeypatch) -> None:
    for name in (
        "ODIN_MEMORY_DB",
        "ODIN_CONVERSATIONS_DB",
        "ODIN_AGENTS_DB",
        "ODIN_REPOSITORY_DB",
        "ODIN_TOOL_DB",
        "ODIN_DATABASE_PATH",
        "DATABASE_PATH",
        "ODIN_AUTH_DB",
    ):
        monkeypatch.delenv(name, raising=False)


def test_odin_memory_db_is_canonical_for_active_backend_persistence(tmp_path: Path, monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    shared_path = (tmp_path / "shared-memory.db").resolve()
    monkeypatch.setenv("ODIN_MEMORY_DB", str(shared_path))
    monkeypatch.setenv("ODIN_CONVERSATIONS_DB", str(tmp_path / "legacy-conversations.db"))
    monkeypatch.setenv("ODIN_AGENTS_DB", str(tmp_path / "legacy-agents.db"))
    monkeypatch.setenv("ODIN_REPOSITORY_DB", str(tmp_path / "legacy-repositories.db"))
    monkeypatch.setenv("ODIN_TOOL_DB", str(tmp_path / "legacy-tools.db"))
    monkeypatch.setenv("ODIN_DATABASE_PATH", str(tmp_path / "legacy-storage.db"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "legacy-database-path.db"))
    monkeypatch.setenv("ODIN_AUTH_DB", str(tmp_path / "legacy-auth.db"))
    monkeypatch.setenv("ODIN_REPOSITORY_WORKSPACE_ROOT", str(tmp_path / "workspaces"))

    assert get_conversation_settings().database_path == shared_path
    assert get_agent_settings().database_path == shared_path
    assert get_memory_settings().database_path == shared_path
    assert get_repository_settings().database_path == shared_path
    assert get_tool_settings().database_path == shared_path
    assert resolve_database_path() == shared_path
    assert resolve_intelligence_repository_db() == shared_path
    assert resolve_api_repository_db() == shared_path
    assert TaskWorkspaceService(root=tmp_path / "change-tasks").db_path == shared_path


def test_legacy_database_envs_remain_supported_when_canonical_is_unset(tmp_path: Path, monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    conversations_path = (tmp_path / "conversations.db").resolve()
    agents_path = (tmp_path / "agents.db").resolve()
    repositories_path = (tmp_path / "repositories.db").resolve()
    tools_path = (tmp_path / "tools.db").resolve()
    storage_path = (tmp_path / "storage.db").resolve()

    monkeypatch.setenv("ODIN_CONVERSATIONS_DB", str(conversations_path))
    monkeypatch.setenv("ODIN_AGENTS_DB", str(agents_path))
    monkeypatch.setenv("ODIN_REPOSITORY_DB", str(repositories_path))
    monkeypatch.setenv("ODIN_TOOL_DB", str(tools_path))
    monkeypatch.setenv("ODIN_DATABASE_PATH", str(storage_path))
    monkeypatch.setenv("ODIN_REPOSITORY_WORKSPACE_ROOT", str(tmp_path / "workspaces"))

    assert get_conversation_settings().database_path == conversations_path
    assert get_agent_settings().database_path == agents_path
    assert get_repository_settings().database_path == repositories_path
    assert get_tool_settings().database_path == tools_path
    assert resolve_database_path() == storage_path
    assert resolve_intelligence_repository_db() == repositories_path
    assert resolve_api_repository_db() == repositories_path
    assert TaskWorkspaceService(root=tmp_path / "change-tasks").db_path == repositories_path


def test_backend_defaults_converge_on_memory_db(monkeypatch) -> None:
    _clear_database_env(monkeypatch)

    expected_default = (
        Path(__file__).resolve().parents[1] / "data" / "memory.db"
    ).resolve()

    assert get_conversation_settings().database_path == expected_default
    assert get_agent_settings().database_path == expected_default
    assert get_memory_settings().database_path == expected_default
    assert get_repository_settings().database_path == expected_default
    assert get_tool_settings().database_path == expected_default
    assert resolve_database_path() == expected_default
    assert resolve_intelligence_repository_db() == expected_default
    assert resolve_api_repository_db() == expected_default
