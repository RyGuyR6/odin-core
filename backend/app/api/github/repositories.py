from fastapi import APIRouter, HTTPException, Query

from app.services.github.repositories import RepositoryService
from app.services.github.provider import GitHubProvider

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

repos = GitHubProvider().repositories


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