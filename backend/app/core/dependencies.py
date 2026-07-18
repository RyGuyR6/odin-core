"""
Application dependency providers.
"""

from app.services.github.repositories import RepositoryService
from app.services.github.branches import BranchService
from app.services.github.commits import CommitService
from app.services.github.pull_requests import PullRequestService


def get_repository_service() -> RepositoryService:
    return RepositoryService()


def get_branch_service() -> BranchService:
    return BranchService()


def get_commit_service() -> CommitService:
    return CommitService()


def get_pull_request_service() -> PullRequestService:
    return PullRequestService()
