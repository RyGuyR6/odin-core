#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENGINEERING="$ROOT/backend/app/services/engineering"

mkdir -p "$ENGINEERING"

############################################
# __init__.py
############################################

cat > "$ENGINEERING/__init__.py" <<'PYTHON'
from .service import EngineeringService
PYTHON

############################################
# service.py
############################################

cat > "$ENGINEERING/service.py" <<'PYTHON'
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
PYTHON

echo
echo "======================================"
echo " Engineering Layer Installed"
echo "======================================"
echo
echo "Created:"
echo " backend/app/services/engineering/"
echo
echo " EngineeringService"
echo