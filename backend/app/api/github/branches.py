from fastapi import APIRouter, HTTPException

from app.services.github.branches import BranchService
from app.services.github.provider import GitHubProvider

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

branches = GitHubProvider().branches


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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