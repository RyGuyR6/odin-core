"""Approval-gated Git orchestration for OIC-016."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories.models import CommitRequest, PushRequest


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
        record, path = self.repositories.require(context.workspace_id)
        actual = self.repositories.git.head_sha(path)
        if not actual or actual != context.expected_head_sha:
            raise AutonomousGitError(
                "Workspace HEAD changed after the operation was planned"
            )
        return record, path

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
        _, path = self._bound_workspace(context)
        branch = self._require_feature_branch(branch)
        self.repositories.git.create_branch(
            path, branch, start_point=context.expected_head_sha, checkout=checkout
        )
        self.repositories.store.record_event(
            context.workspace_id,
            "autonomous_git.branch_created",
            context.actor,
            {"branch": branch, "base_sha": context.expected_head_sha},
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
        validation: dict[str, Any],
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        record, path = self._bound_workspace(context)
        branch = self._require_feature_branch(
            self.repositories.git.current_branch(path)
        )
        if validation.get("status") != "passed":
            raise AutonomousGitError("A successful validation is required before commit")
        if validation.get("head_sha") != context.expected_head_sha:
            raise AutonomousGitError(
                "Validation is stale relative to the current workspace HEAD"
            )
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
        result = self.repositories.commit(
            context.workspace_id,
            CommitRequest(message=message, paths=commit_paths),
            actor_id=context.actor,
        )
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
        result = self.repositories.push(
            context.workspace_id,
            PushRequest(remote=remote, branch=branch, set_upstream=True),
            actor_id=context.actor,
        )
        return {**result, "approved": True, "expected_head_sha": context.expected_head_sha}

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
    ) -> dict[str, Any]:
        self._require_approval(approved, "Pull request creation")
        _, path = self._bound_workspace(context)
        head = self._require_feature_branch(
            self.repositories.git.current_branch(path)
        )
        if self.github is None:
            raise AutonomousGitError("GitHub provider is not configured")
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
        validation: dict[str, Any],
        notes: str = "",
    ) -> dict[str, Any]:
        record, path = self._bound_workspace(context)
        version = version.strip()
        if not version or any(character.isspace() for character in version):
            raise AutonomousGitError("A whitespace-free release version is required")
        if validation.get("status") != "passed":
            raise AutonomousGitError("Release preparation requires passing validation")
        if validation.get("head_sha") != context.expected_head_sha:
            raise AutonomousGitError(
                "Release validation is stale relative to the current workspace HEAD"
            )
        if not self.repositories.git.status(path).clean:
            raise AutonomousGitError("Release preparation requires a clean workspace")
        return {
            "operation": "release.prepare",
            "workspace_id": context.workspace_id,
            "version": version,
            "head_sha": context.expected_head_sha,
            "branch": record.current_branch,
            "notes": notes,
            "validation": dict(validation),
            "tag_created": False,
            "release_created": False,
            "requires_approval_for_publication": True,
        }
