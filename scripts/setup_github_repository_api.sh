#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/backend/app/api/github.py"

echo "========================================="
echo " Sprint 37 - GitHub Repository API"
echo "========================================="
echo

if [ ! -f "$API" ]; then
    echo "ERROR: github.py not found."
    exit 1
fi

cat > "$API" <<'PYTHON'
"""
GitHub API Router
"""

from fastapi import APIRouter, HTTPException, Query

from app.services.github_service import GitHubService

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

service = GitHubService()


def handle(func):
    try:
        return func()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/me")
def current_user():
    return handle(service.get_current_user)


@router.get("/repos")
def repositories():
    return handle(service.list_repositories)


@router.get("/repo/{owner}/{repo}")
def repository(owner: str, repo: str):
    return handle(lambda: service.get_repository(owner, repo))


@router.get("/repo/{owner}/{repo}/branches")
def branches(owner: str, repo: str):
    return handle(lambda: service.list_branches(owner, repo))


@router.get("/repo/{owner}/{repo}/file")
def file(
    owner: str,
    repo: str,
    path: str = Query(...),
):
    return handle(lambda: service.get_file(owner, repo, path))
PYTHON

echo
echo "========================================="
echo " Sprint 37 Complete"
echo "========================================="
echo
echo "GitHub API expanded successfully."
echo