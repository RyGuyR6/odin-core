from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import tools as tools_api
from app.main import app
from app.tools.base import Tool
from app.tools.manager import ToolManager, get_tool_manager
from app.tools.models import ExecutionContext, ToolDefinition, ToolExecutionRequest


def build_manager(tmp_path: Path, monkeypatch, *, allow_shell: bool = False) -> ToolManager:
    monkeypatch.setenv("ODIN_TOOL_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("ODIN_TOOL_DB", str(tmp_path / "tools.db"))
    monkeypatch.setenv("ODIN_TOOL_ALLOW_SHELL", "true" if allow_shell else "false")
    monkeypatch.setenv("ODIN_TOOL_ALLOW_PYTHON", "true")
    get_tool_manager.cache_clear()
    return ToolManager()


def tool_request(name: str, **arguments) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        tool_name=name,
        arguments=arguments,
        context=ExecutionContext(
            actor_id="tester",
            workspace_id="default",
            permissions={"tools.execute.*"},
        ),
    )


def test_tool_catalog_permissions_and_health(tmp_path, monkeypatch):
    manager = build_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(tools_api, "get_tool_manager", lambda: manager)

    with TestClient(app) as client:
        tools_response = client.get("/tools")
        assert tools_response.status_code == 200
        payload = tools_response.json()
        names = {tool["name"] for tool in payload["tools"]}
        assert "filesystem.read" in names
        assert "terminal.execute" in names
        assert "git.status" in names
        assert "github.repositories" in names
        assert "repository.symbol_search" in names
        assert "web.search" in names

        permissions_response = client.get("/tools/permissions")
        assert permissions_response.status_code == 200
        permissions = permissions_response.json()
        terminal = next(
            item
            for item in permissions["permissions"]
            if item["tool_name"] == "terminal.execute"
        )
        assert terminal["permission_level"] == "approval_required"
        assert "tools.execute.terminal.execute" in terminal["required_permissions"]

        health_response = client.get("/tools/health")
        assert health_response.status_code == 200
        github_health = next(
            item
            for item in health_response.json()["tools"]
            if item["tool_name"] == "github.repositories"
        )
        assert github_health["status"] in {"healthy", "degraded"}


def test_tool_approval_flow_and_execution_history(tmp_path, monkeypatch):
    manager = build_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(tools_api, "get_tool_manager", lambda: manager)

    with TestClient(app) as client:
        execute_response = client.post(
            "/tools/execute",
            json=tool_request(
                "filesystem.write", path="notes.txt", content="hello odin", overwrite=True
            ).model_dump(mode="json"),
        )
        assert execute_response.status_code == 200
        execution = execute_response.json()
        assert execution["status"] == "awaiting_approval"
        approval_id = execution["approval_id"]

        approvals_response = client.get("/tools/approvals?status=pending")
        assert approvals_response.status_code == 200
        assert approvals_response.json()["count"] == 1

        decision_response = client.post(
            f"/tools/approvals/{approval_id}/decision",
            json={"approved": True, "decided_by": "reviewer", "note": "safe change"},
        )
        assert decision_response.status_code == 200
        assert decision_response.json()["status"] == "approved"

        approved_execution = client.post(
            f"/tools/approvals/{approval_id}/execute",
            json=tool_request("filesystem.write").context.model_dump(mode="json"),
        )
        assert approved_execution.status_code == 200
        resumed = approved_execution.json()
        assert resumed["status"] == "succeeded"

        events_response = client.get(f"/tools/executions/{execution['id']}/events")
        assert events_response.status_code == 200
        event_types = {event["event_type"] for event in events_response.json()["events"]}
        assert "approval.requested" in event_types


def test_terminal_git_and_retry_execution(tmp_path, monkeypatch):
    manager = build_manager(tmp_path, monkeypatch, allow_shell=True)
    workspace = manager.sandbox.workspace("default")
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    (workspace / "README.md").write_text("odin\n", encoding="utf-8")

    terminal_record = subprocess.run(
        ["git", "status", "--short"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "README.md" in terminal_record.stdout

    result = manager.store.list_executions()
    assert result == []

    async def run_terminal():
        return await manager.executor.execute(
            tool_request(
                "terminal.execute",
                argv=["git", "status", "--short"],
                stream=True,
            )
        )

    async def run_git_status():
        return await manager.executor.execute(tool_request("git.status"))

    class FlakyTool(Tool):
        definition = ToolDefinition(
            name="test.flaky",
            description="Fails once before succeeding.",
            category="test",
            max_retries=1,
        )

        def __init__(self):
            self.calls = 0

        async def execute(self, arguments, context):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("retry me")
            return {"ok": True}

    flaky = FlakyTool()
    manager.registry.register(flaky, replace=True)

    async def run_flaky():
        return await manager.executor.execute(tool_request("test.flaky"))

    import asyncio

    terminal_execution = asyncio.run(run_terminal())
    git_execution = asyncio.run(run_git_status())
    flaky_execution = asyncio.run(run_flaky())

    assert terminal_execution.status.value == "succeeded"
    assert "README.md" in terminal_execution.result["stdout"]
    assert git_execution.status.value == "succeeded"
    assert "##" in git_execution.result["stdout"]
    assert flaky_execution.status.value == "succeeded"

    events = manager.store.execution_events(terminal_execution.id, limit=20)
    assert any(event["event_type"] == "execution.output" for event in events)
