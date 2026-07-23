from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.repositories.manager import RepositoryManager
from app.repositories.models import WorkspaceCreate
from app.services.autonomous_git import (
    AutonomousGitError,
    AutonomousGitService,
    GitOperationContext,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def autonomous_git(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ODIN_REPOSITORY_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("ODIN_REPOSITORY_DB", str(tmp_path / "repositories.db"))
    monkeypatch.setenv("ODIN_GIT_ALLOW_PUSH", "true")
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Odin Tests")
    _git(source, "config", "user.email", "odin@example.test")
    (source / "README.md").write_text("base\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-m", "initial")
    manager = RepositoryManager()
    workspace = manager.create(
        WorkspaceCreate(name="autonomous-git", local_path=str(source))
    )
    service = AutonomousGitService(manager)
    return service, manager, workspace


def _context(manager, workspace):
    _, path = manager.require(workspace.id)
    return GitOperationContext(
        workspace_id=workspace.id,
        expected_head_sha=manager.git.head_sha(path),
        actor="tester",
    )


def test_branch_creation_is_sha_bound_and_protects_main(autonomous_git):
    service, manager, workspace = autonomous_git
    context = _context(manager, workspace)
    result = service.create_branch(context, branch="agent/oic-016")
    assert result["branch"] == "agent/oic-016"
    with pytest.raises(AutonomousGitError, match="protected branch"):
        service.create_branch(context, branch="main")


def test_stale_head_fails_closed(autonomous_git):
    service, manager, workspace = autonomous_git
    context = _context(manager, workspace)
    _, path = manager.require(workspace.id)
    _git(path, "commit", "--allow-empty", "-m", "move head")
    with pytest.raises(AutonomousGitError, match="HEAD changed"):
        service.create_branch(context, branch="agent/stale")


def test_commit_requires_current_successful_validation(autonomous_git):
    service, manager, workspace = autonomous_git
    context = _context(manager, workspace)
    service.create_branch(context, branch="agent/validated")
    _, path = manager.require(workspace.id)
    (path / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(AutonomousGitError, match="successful validation"):
        service.commit(context, message="change", validation={"status": "failed"})
    with pytest.raises(AutonomousGitError, match="stale"):
        service.commit(
            context,
            message="change",
            validation={"status": "passed", "head_sha": "wrong"},
        )
    result = service.commit(
        context,
        message="change",
        validation={"status": "passed", "head_sha": context.expected_head_sha},
    )
    assert result["branch"] == "agent/validated"
    assert result["sha"] != context.expected_head_sha


def test_remote_mutations_require_approval(autonomous_git):
    service, manager, workspace = autonomous_git
    context = _context(manager, workspace)
    service.create_branch(context, branch="agent/remote")
    with pytest.raises(AutonomousGitError, match="approved execution"):
        service.push(context, approved=False)
    with pytest.raises(AutonomousGitError, match="approved execution"):
        service.create_draft_pull_request(
            context,
            approved=False,
            owner="owner",
            repo="repo",
            title="Title",
            base="main",
        )


def test_pull_request_is_always_draft(autonomous_git):
    _, manager, workspace = autonomous_git
    context = _context(manager, workspace)
    calls = []
    pull_requests = SimpleNamespace(
        create_pull_request=lambda *args, **kwargs: calls.append((args, kwargs))
        or {"executed": True}
    )
    service = AutonomousGitService(
        manager, SimpleNamespace(pull_requests=pull_requests)
    )
    service.create_branch(context, branch="agent/pr")
    result = service.create_draft_pull_request(
        context,
        approved=True,
        owner="owner",
        repo="repo",
        title="OIC-016",
        base="main",
    )
    assert result["executed"] is True
    assert calls[0][1]["draft"] is True
    assert calls[0][1]["confirmed"] is True
    assert calls[0][1]["dry_run"] is False


def test_readiness_requires_checks_and_reviews():
    observed = {}

    class PullRequests:
        def evaluate_review_gates(self, *args, **kwargs):
            observed.update(kwargs)
            return SimpleNamespace(as_dict=lambda: {"passed": False})

    service = AutonomousGitService(
        SimpleNamespace(), SimpleNamespace(pull_requests=PullRequests())
    )
    assert service.readiness(
        owner="owner", repo="repo", number=16, required_approvals=2
    ) == {"passed": False}
    assert observed == {"required_approvals": 2, "require_checks": True}


def test_release_preparation_is_non_mutating_and_sha_bound(autonomous_git):
    service, manager, workspace = autonomous_git
    context = _context(manager, workspace)
    plan = service.prepare_release(
        context,
        version="v1.0.0",
        validation={"status": "passed", "head_sha": context.expected_head_sha},
        notes="First release",
    )
    assert plan["tag_created"] is False
    assert plan["release_created"] is False
    assert plan["requires_approval_for_publication"] is True
