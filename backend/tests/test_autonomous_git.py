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
from app.services.task_workspaces import TaskWorkspaceService


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
    record = SimpleNamespace(
        id=workspace.id,
        current_branch="main",
        validation_runs=[],
    )

    class Workspaces:
        git = manager.git
        working_tree_fingerprint = TaskWorkspaceService.working_tree_fingerprint

        def get_workspace(self, workspace_id):
            assert workspace_id == workspace.id
            return record

        def _workspace_root(self, _record):
            return Path(workspace.path)

    service = AutonomousGitService(Workspaces())
    return service, manager, workspace, record, Workspaces()


def _context(manager, workspace):
    _, path = manager.require(workspace.id)
    return GitOperationContext(
        workspace_id=workspace.id,
        expected_head_sha=manager.git.head_sha(path),
        actor="tester",
    )


def test_branch_creation_is_sha_bound_and_protects_main(autonomous_git):
    service, manager, workspace, _, _ = autonomous_git
    context = _context(manager, workspace)
    result = service.create_branch(context, branch="agent/oic-016")
    assert result["branch"] == "agent/oic-016"
    with pytest.raises(AutonomousGitError, match="protected branch"):
        service.create_branch(context, branch="main")


def test_stale_head_fails_closed(autonomous_git):
    service, manager, workspace, _, _ = autonomous_git
    context = _context(manager, workspace)
    _, path = manager.require(workspace.id)
    _git(path, "commit", "--allow-empty", "-m", "move head")
    with pytest.raises(AutonomousGitError, match="HEAD changed"):
        service.create_branch(context, branch="agent/stale")


def test_commit_requires_current_successful_validation(autonomous_git):
    service, manager, workspace, record, _ = autonomous_git
    context = _context(manager, workspace)
    service.create_branch(context, branch="agent/validated")
    _, path = manager.require(workspace.id)
    (path / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(AutonomousGitError, match="persisted successful"):
        service.commit(context, message="change")
    record.validation_runs.append(
        SimpleNamespace(
            id="forged-failed", timestamp="2026-07-23T00:00:00+00:00",
            status="failed", head_sha=context.expected_head_sha,
            working_tree_fingerprint=service.repositories.working_tree_fingerprint(path),
        )
    )
    with pytest.raises(AutonomousGitError, match="persisted successful"):
        service.commit(context, message="change")
    record.validation_runs[-1].status = "succeeded"
    result = service.commit(context, message="change")
    assert result["branch"] == "agent/validated"
    assert result["sha"] != context.expected_head_sha


def test_commit_rejects_working_tree_changed_after_validation(autonomous_git):
    service, manager, workspace, record, _ = autonomous_git
    context = _context(manager, workspace)
    service.create_branch(context, branch="agent/fingerprint")
    _, path = manager.require(workspace.id)
    target = path / "README.md"
    target.write_text("validated\n", encoding="utf-8")
    record.validation_runs.append(
        SimpleNamespace(
            id="validated-tree",
            timestamp="2026-07-23T00:00:00+00:00",
            status="succeeded",
            head_sha=context.expected_head_sha,
            working_tree_fingerprint=service.repositories.working_tree_fingerprint(path),
        )
    )
    target.write_text("changed after validation\n", encoding="utf-8")
    with pytest.raises(AutonomousGitError, match="exact working tree"):
        service.commit(context, message="must fail")


def test_remote_mutations_require_approval(autonomous_git):
    service, manager, workspace, _, _ = autonomous_git
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
    _, manager, workspace, _, workspaces = autonomous_git
    context = _context(manager, workspace)
    calls = []
    pull_requests = SimpleNamespace(
        create_pull_request=lambda *args, **kwargs: calls.append((args, kwargs))
        or {"executed": True}
    )
    branches = SimpleNamespace(
        get_branch=lambda owner, repo, branch: {
            "commit": {"sha": context.expected_head_sha}
        }
    )
    _, path = manager.require(workspace.id)
    _git(path, "remote", "add", "origin", "https://github.com/owner/repo.git")
    service = AutonomousGitService(
        workspaces, SimpleNamespace(pull_requests=pull_requests, branches=branches)
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
    service, manager, workspace, record, _ = autonomous_git
    context = _context(manager, workspace)
    record.validation_runs.append(
        SimpleNamespace(
            id="release-validation", timestamp="2026-07-23T00:00:00+00:00",
            status="succeeded", head_sha=context.expected_head_sha,
            working_tree_fingerprint=service.repositories.working_tree_fingerprint(
                manager.require(workspace.id)[1]
            ),
        )
    )
    plan = service.prepare_release(
        context,
        version="v1.0.0",
        notes="First release",
    )
    assert plan["tag_created"] is False
    assert plan["release_created"] is False
    assert plan["requires_approval_for_publication"] is True


def test_pull_request_rejects_mismatched_repository(autonomous_git):
    _, manager, workspace, _, workspaces = autonomous_git
    context = _context(manager, workspace)
    _, path = manager.require(workspace.id)
    _git(path, "remote", "add", "origin", "https://github.com/right/repo.git")
    service = AutonomousGitService(
        workspaces,
        SimpleNamespace(
            branches=SimpleNamespace(get_branch=lambda *args: {}),
            pull_requests=SimpleNamespace(create_pull_request=lambda *args, **kwargs: {}),
        ),
    )
    service.create_branch(context, branch="agent/mismatch")
    with pytest.raises(AutonomousGitError, match="does not match"):
        service.create_draft_pull_request(
            context, approved=True, owner="wrong", repo="repo",
            title="Mismatch", base="main"
        )


def test_pull_request_rejects_stale_remote_branch_head(autonomous_git):
    _, manager, workspace, _, workspaces = autonomous_git
    context = _context(manager, workspace)
    _, path = manager.require(workspace.id)
    _git(path, "remote", "add", "origin", "https://github.com/owner/repo.git")
    service = AutonomousGitService(
        workspaces,
        SimpleNamespace(
            branches=SimpleNamespace(
                get_branch=lambda *args: {"commit": {"sha": "stale"}}
            ),
            pull_requests=SimpleNamespace(create_pull_request=lambda *args, **kwargs: {}),
        ),
    )
    service.create_branch(context, branch="agent/stale-remote")
    with pytest.raises(AutonomousGitError, match="Remote branch HEAD"):
        service.create_draft_pull_request(
            context, approved=True, owner="owner", repo="repo",
            title="Stale", base="main"
        )
