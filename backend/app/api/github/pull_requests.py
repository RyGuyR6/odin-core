from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.github.dependencies import get_pull_request_service
from app.api.github.errors import github_http_error
from app.services.github.pull_requests import PullRequestService

router = APIRouter(prefix="/github", tags=["GitHub"])


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.post("/repo/{owner}/{repo}/pull-request")
def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.create_pull_request(owner, repo, title, head, base, body))
