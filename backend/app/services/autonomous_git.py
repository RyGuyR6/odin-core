"""Approval-gated Git orchestration for OIC-016."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class AutonomousGitError(ValueError):
    """Raised when an autonomous Git safety invariant is violated."""


@dataclass(frozen=True)
class GitOperationContext:
    workspace_id: str
    expected_head_sha: str
    actor: str = "execution"


class AutonomousGitService:
    """Coordinates existing local and remote Git primitives behind safety gates."""

    PROTECTED_BRANCHES = frozenset(
        {"main", "master", "production", "prod", "release"}
    )

    def __init__(self, repository_manager: Any, github_provider: Any = None):
        self.repositories = repository_manager
        self.github = github_provider

    def _bound_workspace(self, context: GitOperationContext):
        record = self.repositories.get_workspace(context.workspace_id)
        path = self.repositories._workspace_root(record)
        actual = self.repositories.git.head_sha(path)
        if not actual or actual != context.expected_head_sha:
            raise AutonomousGitError(
                "Workspace HEAD changed after the operation was planned"
            )
        return record, path

    def _audit(
        self,
        record: Any,
        event: str,
        context: GitOperationContext,
        **details: Any,
    ) -> None:
        event_writer = getattr(self.repositories, "_event", None)
        store = getattr(self.repositories, "store", None)
        if callable(event_writer) and store is not None:
            event_writer(record, event, actor=context.actor, **details)
            store.save(record)

    def _persisted_validation(
        self, record: Any, expected_head_sha: str
    ) -> dict[str, Any]:
        matching = [
            run
            for run in record.validation_runs
            if run.head_sha == expected_head_sha
        ]
        if not matching or any(run.status != "succeeded" for run in matching):
            raise AutonomousGitError(
                "A persisted successful workspace validation for the exact HEAD is required"
            )
        latest_timestamp = max(run.timestamp for run in matching)
        return {
            "status": "passed",
            "head_sha": expected_head_sha,
            "run_ids": [run.id for run in matching],
            "validated_at": latest_timestamp,
        }

    @staticmethod
    def _github_repository(remote_url: str) -> tuple[str, str]:
        value = remote_url.strip()
        if value.startswith("git@github.com:"):
            path = value.removeprefix("git@github.com:")
        else:
            parsed = urlparse(value)
            if parsed.hostname != "github.com":
                raise AutonomousGitError("Remote must be hosted on github.com")
            path = parsed.path.lstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.split("/")
        if len(parts) != 2 or not all(parts):
            raise AutonomousGitError("Remote does not identify one GitHub repository")
        return parts[0], parts[1]

    def _bound_remote(
        self, path: Any, remote: str, owner: str | None = None, repo: str | None = None
    ) -> tuple[str, str]:
        remotes = self.repositories.git.remotes(path)
        if remote not in remotes:
            raise AutonomousGitError(f"Configured Git remote not found: {remote}")
        remote_owner, remote_repo = self._github_repository(remotes[remote])
        if owner is not None and repo is not None and (
            remote_owner.casefold(),
            remote_repo.casefold(),
        ) != (owner.casefold(), repo.casefold()):
            raise AutonomousGitError(
                "Pull request repository does not match the workspace Git remote"
            )
        return remote_owner, remote_repo

    @classmethod
    def _require_feature_branch(cls, branch: str | None) -> str:
        value = (branch or "").strip()
        if not value:
            raise AutonomousGitError("A named branch is required")
        if value.lower() in cls.PROTECTED_BRANCHES or value.lower().startswith(
            ("release/", "production/")
        ):
            raise AutonomousGitError(
                f"Direct autonomous mutation of protected branch '{value}' is forbidden"
            )
        return value

    @staticmethod
    def _require_approval(approved: bool, operation: str) -> None:
        if not approved:
            raise AutonomousGitError(
                f"{operation} requires an approved execution checkpoint"
            )

    def create_branch(
        self,
        context: GitOperationContext,
        *,
        branch: str,
        checkout: bool = True,
    ) -> dict[str, Any]:
        record, path = self._bound_workspace(context)
        branch = self._require_feature_branch(branch)
        self.repositories.git.create_branch(
            path, branch, start_point=context.expected_head_sha, checkout=checkout
        )
        self._audit(
            record,
            "autonomous_git.branch_created",
            context,
            branch=branch,
            base_sha=context.expected_head_sha,
        )
        return {
            "workspace_id": context.workspace_id,
            "branch": branch,
            "base_sha": context.expected_head_sha,
            "head_sha": self.repositories.git.head_sha(path),
        }

    def commit(
        self,
        context: GitOperationContext,
        *,
        message: str,
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        record, path = self._bound_workspace(context)
        branch = self._require_feature_branch(
            self.repositories.git.current_branch(path)
        )
        validation = self._persisted_validation(record, context.expected_head_sha)
        status = self.repositories.git.status(path)
        if status.clean:
            raise AutonomousGitError("Workspace has no changes to commit")
        commit_paths = paths
        if commit_paths is None:
            commit_paths = sorted(
                {
                    entry.path
                    for entry in status.entries
                }
                | {
                    entry.original_path
                    for entry in status.entries
                    if entry.original_path
                }
            )
        self.repositories.git.add(path, commit_paths)
        sha = self.repositories.git.commit(path, message)
        result = {"sha": sha}
        return {
            **result,
            "workspace_id": context.workspace_id,
            "base_sha": context.expected_head_sha,
            "validation": dict(validation),
            "branch": branch,
        }

    def push(
        self,
        context: GitOperationContext,
        *,
        approved: bool,
        remote: str = "origin",
    ) -> dict[str, Any]:
        self._require_approval(approved, "Git push")
        _, path = self._bound_workspace(context)
        branch = self._require_feature_branch(
            self.repositories.git.current_branch(path)
        )
        owner, repo = self._bound_remote(path, remote)
        self.repositories.git.push(path, remote, branch, True, False)
        return {
            "remote": remote,
            "repository": f"{owner}/{repo}",
            "branch": branch,
            "head_sha": context.expected_head_sha,
            "approved": True,
            "expected_head_sha": context.expected_head_sha,
        }

    def create_draft_pull_request(
        self,
        context: GitOperationContext,
        *,
        approved: bool,
        owner: str,
        repo: str,
        title: str,
        base: str,
        body: str = "",
        remote: str = "origin",
    ) -> dict[str, Any]:
        self._require_approval(approved, "Pull request creation")
        _, path = self._bound_workspace(context)
        head = self._require_feature_branch(
            self.repositories.git.current_branch(path)
        )
        if self.github is None:
            raise AutonomousGitError("GitHub provider is not configured")
        self._bound_remote(path, remote, owner, repo)
        remote_branch = self.github.branches.get_branch(owner, repo, head)
        remote_sha = ((remote_branch or {}).get("commit") or {}).get("sha")
        if remote_sha != context.expected_head_sha:
            raise AutonomousGitError(
                "Remote branch HEAD does not match the approved workspace commit"
            )
        return self.github.pull_requests.create_pull_request(
            owner,
            repo,
            title,
            head,
            base,
            body,
            draft=True,
            confirmed=True,
            dry_run=False,
        )

    def readiness(
        self,
        *,
        owner: str,
        repo: str,
        number: int,
        required_approvals: int = 1,
    ) -> dict[str, Any]:
        if self.github is None:
            raise AutonomousGitError("GitHub provider is not configured")
        return self.github.pull_requests.evaluate_review_gates(
            owner,
            repo,
            number,
            required_approvals=required_approvals,
            require_checks=True,
        ).as_dict()

    def prepare_release(
        self,
        context: GitOperationContext,
        *,
        version: str,
        notes: str = "",
    ) -> dict[str, Any]:
        record, path = self._bound_workspace(context)
        version = version.strip()
        if not version or any(character.isspace() for character in version):
            raise AutonomousGitError("A whitespace-free release version is required")
        validation = self._persisted_validation(record, context.expected_head_sha)
        if not self.repositories.git.status(path).clean:
            raise AutonomousGitError("Release preparation requires a clean workspace")
        return {
            "operation": "release.prepare",
            "workspace_id": context.workspace_id,
            "version": version,
            "head_sha": context.expected_head_sha,
            "branch": self.repositories.git.current_branch(path),
            "notes": notes,
            "validation": dict(validation),
            "tag_created": False,
            "release_created": False,
            "requires_approval_for_publication": True,
        }
