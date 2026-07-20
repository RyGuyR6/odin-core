from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.github.dependencies import get_pull_request_service
from app.api.github.errors import github_http_error
from app.services.github.pull_requests import PullRequestService

router = APIRouter(prefix="/github", tags=["GitHub"])


class PullRequestCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    head: str
    base: str
    body: str = ""
    draft: bool = False
    confirmed: bool = False
    dry_run: bool = True


class PullRequestMergeRequest(BaseModel):
    method: str = "squash"
    commit_title: str | None = None
    commit_message: str | None = None
    required_approvals: int = Field(default=1, ge=0)
    require_checks: bool = True
    confirmed: bool = False
    dry_run: bool = True


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.post("/repo/{owner}/{repo}/pull-request")
def create_pull_request(
    owner: str,
    repo: str,
    request: PullRequestCreateRequest,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.create_pull_request(
        owner,
        repo,
        request.title,
        request.head,
        request.base,
        request.body,
        draft=request.draft,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))


@router.get("/repo/{owner}/{repo}/pull-request/{number}")
def get_pull_request(
    owner: str,
    repo: str,
    number: int,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.get_pull_request(owner, repo, number))


@router.get("/repo/{owner}/{repo}/pull-request/{number}/files")
def list_pull_request_files(
    owner: str,
    repo: str,
    number: int,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.list_files(owner, repo, number))


@router.get("/repo/{owner}/{repo}/pull-request/{number}/gates")
def evaluate_pull_request_gates(
    owner: str,
    repo: str,
    number: int,
    required_approvals: int = 1,
    require_checks: bool = True,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.evaluate_review_gates(
        owner,
        repo,
        number,
        required_approvals=required_approvals,
        require_checks=require_checks,
    ).as_dict())


@router.put("/repo/{owner}/{repo}/pull-request/{number}/merge")
def merge_pull_request(
    owner: str,
    repo: str,
    number: int,
    request: PullRequestMergeRequest,
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.merge_pull_request(
        owner,
        repo,
        number,
        method=request.method,
        commit_title=request.commit_title,
        commit_message=request.commit_message,
        required_approvals=request.required_approvals,
        require_checks=request.require_checks,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))
