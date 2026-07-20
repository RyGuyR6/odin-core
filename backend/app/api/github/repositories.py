from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.github.dependencies import get_repository_service
from app.api.github.errors import github_http_error
from app.services.github.repositories import RepositoryService

router = APIRouter(prefix="/github", tags=["GitHub"])


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.get("/me")
def current_user(repos: RepositoryService = Depends(get_repository_service)):
    return run(repos.current_user)


@router.get("/repos")
def repositories(repos: RepositoryService = Depends(get_repository_service)):
    return run(repos.repositories)


@router.get("/repo/{owner}/{repo}")
def repository(
    owner: str,
    repo: str,
    repos: RepositoryService = Depends(get_repository_service),
):
    return run(lambda: repos.repository(owner, repo))


@router.get("/repo/{owner}/{repo}/branches")
def list_branches(
    owner: str,
    repo: str,
    repos: RepositoryService = Depends(get_repository_service),
):
    return run(lambda: repos.branches(owner, repo))


@router.get("/repo/{owner}/{repo}/file")
def get_file(
    owner: str,
    repo: str,
    path: str = Query(...),
    repos: RepositoryService = Depends(get_repository_service),
):
    return run(lambda: repos.client.get(f"/repos/{owner}/{repo}/contents/{path}"))
