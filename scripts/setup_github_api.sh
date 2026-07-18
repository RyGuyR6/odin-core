#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "========================================="
echo " Sprint 34 - GitHub API Router"
echo "========================================="
echo

if [ ! -d "$BACKEND/app/api" ]; then
    echo "Creating backend/app/api..."
    mkdir -p "$BACKEND/app/api"
fi

echo "[1/2] Creating GitHub API router..."

cat > "$BACKEND/app/api/github.py" <<'PYTHON'
"""
GitHub API Router

Exposes GitHub functionality through FastAPI.
"""

from fastapi import APIRouter, HTTPException

from app.services.github_service import GitHubService

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

service = GitHubService()


@router.get("/me")
def get_current_user():
    """Return the authenticated GitHub user."""
    try:
        return service.get_current_user()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/repos")
def list_repositories():
    """Return repositories for the authenticated user."""
    try:
        return service.list_repositories()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
PYTHON

echo "[2/2] Verifying..."

test -f "$BACKEND/app/api/github.py"

echo
echo "========================================="
echo " Sprint 34 Complete"
echo "========================================="
echo
echo "Created:"
echo "  backend/app/api/github.py"
echo
echo "Next Sprint:"
echo "  Register the GitHub router in FastAPI."
echo