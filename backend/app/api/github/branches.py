from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.github.dependencies import get_branch_service
from app.api.github.errors import github_http_error
from app.services.github.branches import BranchService

router = APIRouter(prefix="/github", tags=["GitHub"])


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.post("/repo/{owner}/{repo}/branch")
def create_branch(
    owner: str,
    repo: str,
    new_branch: str,
    source_sha: str,
    branches: BranchService = Depends(get_branch_service),
):
    return run(lambda: branches.create_branch(owner, repo, new_branch, source_sha))
