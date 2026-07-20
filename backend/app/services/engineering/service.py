from __future__ import annotations

from app.services.github import get_github_provider
from app.services.github.provider import GitHubProvider


class EngineeringService:
    def __init__(self, github: GitHubProvider | None = None):
        provider = github or get_github_provider()
        self.github = provider
        self.repositories = provider.repositories
        self.branches = provider.branches
        self.commits = provider.commits
        self.pull_requests = provider.pull_requests

    def repository_summary(self, owner: str, repo: str):
        repository = self.repositories.repository(owner, repo)
        branches = self.repositories.branches(owner, repo)
        return {"repository": repository, "branches": branches}

    def health(self):
        return {
            "service": "engineering",
            "status": "ready" if self.github.configured else "unconfigured",
        }
