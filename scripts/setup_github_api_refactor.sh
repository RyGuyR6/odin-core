#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

API="$ROOT/backend/app/api/github.py"

echo "========================================="
echo " GitHub Refactor Phase 2"
echo " API Wiring"
echo "========================================="
echo

if [ ! -f "$API" ]; then
    echo "github.py not found."
    exit 1
fi

cat > "$API" <<'PYTHON'
from fastapi import APIRouter, HTTPException, Query

from app.services.github.repositories import RepositoryService
from app.services.github.branches import BranchService
from app.services.github.pull_requests import PullRequestService

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

repos = RepositoryService()
branches = BranchService()
prs = PullRequestService()


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/me")
def current_user():
    return run(repos.current_user)


@router.get("/repos")
def repositories():
    return run(repos.repositories)


@router.get("/repo/{owner}/{repo}")
def repository(owner: str, repo: str):
    return run(lambda: repos.repository(owner, repo))


@router.get("/repo/{owner}/{repo}/branches")
def list_branches(owner: str, repo: str):
    return run(lambda: repos.branches(owner, repo))


@router.get("/repo/{owner}/{repo}/file")
def get_file(
    owner: str,
    repo: str,
    path: str = Query(...),
):
    return run(lambda: repos.file(owner, repo, path))


@router.post("/repo/{owner}/{repo}/branch")
def create_branch(
    owner: str,
    repo: str,
    new_branch: str,
    source_sha: str,
):
    return run(
        lambda: branches.create_branch(
            owner,
            repo,
            new_branch,
            source_sha,
        )
    )


@router.post("/repo/{owner}/{repo}/pull-request")
def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
):
    return run(
        lambda: prs.create_pull_request(
            owner,
            repo,
            title,
            head,
            base,
            body,
        )
    )
PYTHON

echo
echo "========================================="
echo " API Refactor Complete"
echo "========================================="
echo
echo "github.py now uses:"
echo
echo "  RepositoryService"
echo "  BranchService"
echo "  PullRequestService"
echo
echo "The old github_service.py can now be retired"