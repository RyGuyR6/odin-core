from __future__ import annotations

import base64
from urllib.parse import quote

from .client import GitHubClient
from .safety import (
    WriteOperation,
    WritePlan,
    is_protected_branch,
    normalize_repo_path,
    require_confirmation,
    validate_branch_name,
    validate_repository_part,
)


class ContentService:
    def __init__(self, client: GitHubClient):
        self.client = client

    def get_file(self, owner, repo, path, ref=None):
        owner = validate_repository_part(owner, "owner")
        repo = validate_repository_part(repo, "repository")
        path = normalize_repo_path(path)
        endpoint = f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}"
        if ref:
            endpoint += f"?ref={quote(validate_branch_name(ref), safe='')}"
        return self.client.get(endpoint)

    def plan_write(self, owner, repo, path, *, branch, message, sha=None, dry_run=True):
        owner = validate_repository_part(owner, "owner")
        repo = validate_repository_part(repo, "repository")
        path = normalize_repo_path(path)
        branch = validate_branch_name(branch)
        message = message.strip()
        if not message:
            raise ValueError("Commit message is required")
        return WritePlan(
            operation=WriteOperation.UPDATE if sha else WriteOperation.CREATE,
            owner=owner,
            repo=repo,
            path=path,
            branch=branch,
            message=message,
            expected_sha=sha.strip() if sha else None,
            protected_branch=is_protected_branch(branch),
            requires_confirmation=True,
            dry_run=dry_run,
        )

    def write_file(
        self, owner, repo, path, content, *, branch, message,
        sha=None, confirmed=False, dry_run=True,
    ):
        plan = self.plan_write(
            owner, repo, path, branch=branch, message=message, sha=sha, dry_run=dry_run
        )
        if dry_run:
            return {"executed": False, "plan": plan.as_dict()}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        payload = {
            "message": plan.message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": plan.branch,
        }
        if plan.expected_sha:
            payload["sha"] = plan.expected_sha
        result = self.client.put(
            f"/repos/{plan.owner}/{plan.repo}/contents/{quote(plan.path, safe='/')}",
            payload,
        )
        return {"executed": True, "plan": plan.as_dict(), "result": result}

    def delete_file(
        self, owner, repo, path, *, branch, message, sha,
        confirmed=False, dry_run=True,
    ):
        base = self.plan_write(
            owner, repo, path, branch=branch, message=message, sha=sha, dry_run=dry_run
        )
        plan = WritePlan(
            operation=WriteOperation.DELETE,
            owner=base.owner,
            repo=base.repo,
            path=base.path,
            branch=base.branch,
            message=base.message,
            expected_sha=base.expected_sha,
            protected_branch=base.protected_branch,
            requires_confirmation=True,
            dry_run=dry_run,
        )
        if dry_run:
            return {"executed": False, "plan": plan.as_dict()}
        require_confirmation(confirmed=confirmed, dry_run=dry_run)
        result = self.client.delete(
            f"/repos/{plan.owner}/{plan.repo}/contents/{quote(plan.path, safe='/')}",
            {"message": plan.message, "sha": plan.expected_sha, "branch": plan.branch},
        )
        return {"executed": True, "plan": plan.as_dict(), "result": result}
