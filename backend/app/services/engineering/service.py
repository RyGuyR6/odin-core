"""
Engineering Service

Coordinates multiple domain services to complete
higher-level software engineering tasks.
"""

from app.services.github.repositories import RepositoryService
from app.services.github.branches import BranchService
from app.services.github.commits import CommitService
from app.services.github.pull_requests import PullRequestService


class EngineeringService:

    def __init__(self):
        self.repositories = RepositoryService()
        self.branches = BranchService()
        self.commits = CommitService()
        self.pull_requests = PullRequestService()

    def repository_summary(
        self,
        owner: str,
        repo: str,
    ):
        repository = self.repositories.repository(owner, repo)
        branches = self.repositories.branches(owner, repo)

        return {
            "repository": repository,
            "branches": branches,
        }

    def health(self):
        return {
            "service": "engineering",
            "status": "ready",
        }
