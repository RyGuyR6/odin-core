#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GITHUB_DIR="$ROOT/backend/app/services/github"
CORE_DIR="$ROOT/backend/app/core"

mkdir -p "$CORE_DIR"

cat > "$CORE_DIR/dependencies.py" <<'PYTHON'
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
PYTHON

echo
echo "======================================="
echo " Dependencies Created"
echo "======================================="
echo
echo "Created:"
echo "  backend/app/core/dependencies.py"
echo
echo "Next step:"
echo "  Update API routers to use FastAPI Depends()."