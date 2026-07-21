from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.services.change_tasks import ChangeTaskOrchestrator, JsonTaskStore, TaskStatus
from app.services.task_workspaces import (
    TaskWorkspaceService,
    WorkspaceCreateRequest,
    WorkspaceProposalRequest,
    WorkspaceServiceError,
    WorkspaceValidationRequest,
)


CONNECTED_REPOSITORIES_DDL = """
CREATE TABLE connected_repositories (
    id INTEGER PRIMARY KEY,
    github_id INTEGER NOT NULL UNIQUE,
    full_name TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    default_branch TEXT NOT NULL,
    private INTEGER NOT NULL DEFAULT 0,
    html_url TEXT NOT NULL,
    description TEXT,
    connected_by TEXT NOT NULL,
    connected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    local_path TEXT
)
"""


def make_repo(root: Path) -> Path:
    (root / "backend").mkdir(parents=True)
    (root / "frontend").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "backend" / "Makefile").write_text(
        "test:\n\tpython -c \"print('backend-ok')\"\n\nlint:\n\tpython -c \"print('backend-lint')\"\n",
        encoding="utf-8",
    )
    (root / "frontend" / "package.json").write_text(
        json.dumps(
            {
                "name": "frontend",
                "private": True,
                "scripts": {
                    "test": "node -e \"console.log('frontend-test')\"",
                    "typecheck": "node -e \"console.log('frontend-typecheck')\"",
                    "lint": "node -e \"console.log('frontend-lint')\"",
                    "build": "node -e \"console.log('frontend-build')\"",
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "src" / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("# repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "odin@example.com"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Odin"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "initial"], check=True, capture_output=True, text=True)
    return root


def connect_repository(db_path: Path, local_path: Path) -> None:
    now = "2026-07-21T00:00:00+00:00"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(CONNECTED_REPOSITORIES_DDL)
        connection.execute(
            """
            INSERT INTO connected_repositories(
                id, github_id, full_name, owner, name, default_branch, private,
                html_url, description, connected_by, connected_at, updated_at, local_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 1001, "acme/repo", "acme", "repo", "main", 0, "https://github.com/acme/repo", "sample", "tester", now, now, str(local_path)),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def workspace_service(tmp_path: Path) -> TaskWorkspaceService:
    db_path = tmp_path / "odin.db"
    repo_root = make_repo(tmp_path / "source")
    connect_repository(db_path, repo_root)
    return TaskWorkspaceService(root=tmp_path / "workspace-root", db_path=db_path)


def test_workspace_creation_and_apply_isolation(workspace_service: TaskWorkspaceService, tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    workspace = workspace_service.create_workspace(WorkspaceCreateRequest(repository_id=1, task_id="task-1"))
    created = workspace_service.upsert_proposals(
        workspace.id,
        [
            WorkspaceProposalRequest(
                target_path="src/hello.py",
                operation="modify_file",
                proposed_content="print('workspace')\n",
            )
        ],
    )
    assert created.status == "changes_proposed"

    approved = workspace_service.approve(workspace.id)
    assert approved.proposals[0].approval_status == "approved"

    applied = workspace_service.apply(workspace.id)
    assert applied.status == "applied"
    assert (source_root / "src" / "hello.py").read_text(encoding="utf-8") == "print('hello')\n"
    assert workspace_service.read_file(workspace.id, "src/hello.py")["content"] == "print('workspace')\n"


def test_workspace_rejects_traversal_and_symlink_escape(workspace_service: TaskWorkspaceService, tmp_path: Path) -> None:
    workspace = workspace_service.create_workspace(WorkspaceCreateRequest(repository_id=1))
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = Path(workspace.path_internal)
    (root / "escape.txt").symlink_to(outside)

    with pytest.raises(WorkspaceServiceError, match="Path traversal"):
        workspace_service.read_file(workspace.id, "../outside.txt")

    with pytest.raises(WorkspaceServiceError, match="escapes workspace"):
        workspace_service.read_file(workspace.id, "escape.txt")


def test_diff_determinism_partial_approval_and_atomic_stale_conflict(workspace_service: TaskWorkspaceService) -> None:
    workspace = workspace_service.create_workspace(WorkspaceCreateRequest(repository_id=1))
    record = workspace_service.upsert_proposals(
        workspace.id,
        [
            WorkspaceProposalRequest(
                target_path="src/hello.py",
                operation="modify_file",
                proposed_content="print('approved')\n",
            ),
            WorkspaceProposalRequest(
                target_path="src/new.py",
                operation="create_file",
                proposed_content="print('new')\n",
            ),
        ],
    )
    first = workspace_service.get_diff(workspace.id)
    second = workspace_service.get_diff(workspace.id)
    assert first == second

    modify_id = next(proposal.id for proposal in record.proposals if proposal.target_path == "src/hello.py")
    create_id = next(proposal.id for proposal in record.proposals if proposal.target_path == "src/new.py")
    workspace_service.approve(workspace.id, proposal_ids=[modify_id])
    workspace_service.reject(workspace.id, proposal_ids=[create_id])
    applied = workspace_service.apply(workspace.id)
    assert applied.status == "applied"
    assert workspace_service.read_file(workspace.id, "src/hello.py")["content"] == "print('approved')\n"
    with pytest.raises(WorkspaceServiceError, match="File not found"):
        workspace_service.read_file(workspace.id, "src/new.py")

    stale = workspace_service.upsert_proposals(
        workspace.id,
        [
            WorkspaceProposalRequest(
                target_path="src/hello.py",
                operation="modify_file",
                proposed_content="print('stale')\n",
            ),
            WorkspaceProposalRequest(
                target_path="src/extra.py",
                operation="create_file",
                proposed_content="print('extra')\n",
            ),
        ],
    )
    Path(stale.path_internal, "src", "hello.py").write_text("print('changed outside workflow')\n", encoding="utf-8")
    workspace_service.approve(workspace.id)
    with pytest.raises(WorkspaceServiceError, match="Stale content hash"):
        workspace_service.apply(workspace.id)
    with pytest.raises(WorkspaceServiceError, match="File not found"):
        workspace_service.read_file(workspace.id, "src/extra.py")


def test_validation_allowlist_timeout_and_rollback(workspace_service: TaskWorkspaceService) -> None:
    workspace = workspace_service.create_workspace(WorkspaceCreateRequest(repository_id=1))
    workspace_service.upsert_proposals(
        workspace.id,
        [
            WorkspaceProposalRequest(
                target_path="src/hello.py",
                operation="modify_file",
                proposed_content="print('validated')\n",
            )
        ],
    )
    workspace_service.approve(workspace.id)
    workspace_service.apply(workspace.id)

    commands = workspace_service.allowed_validation_commands(workspace.id)
    assert {"backend_test", "backend_lint", "frontend_test", "frontend_typecheck", "frontend_lint", "frontend_build"}.issubset(commands)

    result = workspace_service.run_validation(
        workspace.id,
        WorkspaceValidationRequest(command_ids=["backend_test"]),
    )
    assert result["runs"][0]["status"] == "succeeded"

    Path(workspace.path_internal, "backend", "Makefile").write_text(
        "test:\n\tpython -c \"print('backend-ok')\"\n\nlint:\n\tpython -c \"import time; time.sleep(2)\"\n",
        encoding="utf-8",
    )
    workspace_service.validation_timeout_seconds = 1
    timed_out = workspace_service.run_validation(
        workspace.id,
        WorkspaceValidationRequest(command_ids=["backend_lint"]),
    )
    assert timed_out["runs"][0]["status"] == "timed_out"

    rolled_back = workspace_service.rollback(workspace.id, actor="reviewer", reason="validation failed")
    assert rolled_back.status == "rolled_back"
    assert workspace_service.read_file(workspace.id, "src/hello.py")["content"] == "print('hello')\n"


def test_change_task_integration_pauses_at_workspace_approval_step(tmp_path: Path) -> None:
    orchestrator = ChangeTaskOrchestrator(JsonTaskStore(tmp_path / "tasks"))
    echo = orchestrator.create_task(title="Echo", steps=[{"action": "echo", "parameters": {"message": "ok"}}])
    assert orchestrator.execute(echo.id).status == TaskStatus.SUCCEEDED

    task = orchestrator.create_task(
        title="Workspace approval boundary",
        steps=[
            {
                "action": "workspace.request_approval",
                "parameters": {"workspace_id": "workspace-1", "note": "Stop here"},
            },
            {"action": "echo", "parameters": {"message": "after pause"}},
        ],
    )
    result = orchestrator.execute(task.id)
    assert result.status == TaskStatus.PAUSED
