"""Backward-compatible facade over the canonical GitHub client."""

from __future__ import annotations

from app.services.github.client import GitHubClient


class GitHubService:
    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        session=None,
    ):
        self.client = GitHubClient(
            token=token,
            timeout_seconds=timeout_seconds,
            session=session,
        )

    @property
    def token(self):
        return self.client.token

    @property
    def configured(self) -> bool:
        return self.client.configured

    @property
    def session(self):
        return self.client.session

    def _get(self, endpoint: str):
        return self.client.get(endpoint)

    def _post(self, endpoint: str, payload: dict):
        return self.client.post(endpoint, payload)

    def get_current_user(self):
        return self._get("/user")

    def list_repositories(self):
        return self._get("/user/repos")

    def get_repository(self, owner: str, repo: str):
        return self._get(f"/repos/{owner}/{repo}")

    def list_branches(self, owner: str, repo: str):
        return self._get(f"/repos/{owner}/{repo}/branches")

    def get_file(self, owner: str, repo: str, path: str):
        return self._get(f"/repos/{owner}/{repo}/contents/{path}")

    def get_branch(self, owner: str, repo: str, branch: str):
        return self._get(f"/repos/{owner}/{repo}/git/ref/heads/{branch}")

    def create_branch(
        self,
        owner: str,
        repo: str,
        new_branch: str,
        source_sha: str,
    ):
        return self._post(
            f"/repos/{owner}/{repo}/git/refs",
            {"ref": f"refs/heads/{new_branch}", "sha": source_sha},
        )
