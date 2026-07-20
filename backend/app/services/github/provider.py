from __future__ import annotations

from app.services.github.branches import BranchService
from app.services.github.client import GitHubClient
from app.services.github.commits import CommitService
from app.services.github.contents import ContentService
from app.services.github.pull_requests import PullRequestService
from app.services.github.repositories import RepositoryService


class GitHubProvider:
    """Central access point for GitHub domain services."""

    def __init__(self, client: GitHubClient | None = None):
        self.client = client or GitHubClient()
        self.repositories = RepositoryService(self.client)
        self.branches = BranchService(self.client)
        self.commits = CommitService(self.client)
        self.contents = ContentService(self.client)
        self.pull_requests = PullRequestService(self.client)

    @property
    def configured(self) -> bool:
        return self.client.configured
