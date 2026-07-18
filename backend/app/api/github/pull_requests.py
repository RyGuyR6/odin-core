from fastapi import APIRouter, HTTPException

from app.services.github.pull_requests import PullRequestService
from app.services.github.provider import GitHubProvider

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

prs = GitHubProvider().pull_requests


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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