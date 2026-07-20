from __future__ import annotations

from urllib.parse import quote

from .client import GitHubClient
from .safety import GitHubWriteSafetyError, is_protected_branch, validate_branch_name


class BranchService:
    def __init__(self, client: GitHubClient):
        self.client = client

    def get_branch(self, owner, repo, branch):
        branch = validate_branch_name(branch)
        return self.client.get(f"/repos/{owner}/{repo}/branches/{quote(branch, safe='')}")

    def create_branch(self, owner, repo, new_branch, source_sha, *, allow_protected=False):
        branch = validate_branch_name(new_branch)
        if is_protected_branch(branch) and not allow_protected:
            raise GitHubWriteSafetyError(
                f"Refusing to create protected branch {branch!r} without allow_protected=true"
            )
        if not source_sha or len(source_sha.strip()) < 7:
            raise GitHubWriteSafetyError("source_sha must be a valid commit SHA")
        return self.client.post(
            f"/repos/{owner}/{repo}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": source_sha.strip()},
        )

    def delete_branch(self, owner, repo, branch, *, confirmed=False, allow_protected=False):
        branch = validate_branch_name(branch)
        if is_protected_branch(branch) and not allow_protected:
            raise GitHubWriteSafetyError(f"Refusing to delete protected branch {branch!r}")
        if not confirmed:
            raise GitHubWriteSafetyError("Branch deletion requires confirmed=true")
        return self.client.delete(
            f"/repos/{owner}/{repo}/git/refs/heads/{quote(branch, safe='')}"
        )
