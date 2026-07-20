from __future__ import annotations

from app.services.github import get_github_provider
from app.services.github.branches import BranchService
from app.services.github.pull_requests import PullRequestService
from app.services.github.repositories import RepositoryService


def get_repository_service() -> RepositoryService:
    return get_github_provider().repositories


def get_branch_service() -> BranchService:
    return get_github_provider().branches


def get_pull_request_service() -> PullRequestService:
    return get_github_provider().pull_requests
