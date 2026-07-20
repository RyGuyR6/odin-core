from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.github.dependencies import get_content_service
from app.api.github.errors import github_http_error
from app.services.github.contents import ContentService

router = APIRouter(prefix="/github", tags=["GitHub"])


class FileWriteRequest(BaseModel):
    content: str
    branch: str
    message: str = Field(min_length=1)
    sha: str | None = None
    confirmed: bool = False
    dry_run: bool = True


class FileDeleteRequest(BaseModel):
    branch: str
    message: str = Field(min_length=1)
    sha: str = Field(min_length=7)
    confirmed: bool = False
    dry_run: bool = True


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.get("/repo/{owner}/{repo}/contents/{path:path}")
def get_file(owner: str, repo: str, path: str, ref: str | None = None,
             contents: ContentService = Depends(get_content_service)):
    return run(lambda: contents.get_file(owner, repo, path, ref=ref))


@router.put("/repo/{owner}/{repo}/contents/{path:path}")
def write_file(owner: str, repo: str, path: str, request: FileWriteRequest,
               contents: ContentService = Depends(get_content_service)):
    return run(lambda: contents.write_file(
        owner, repo, path, request.content,
        branch=request.branch,
        message=request.message,
        sha=request.sha,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))


@router.delete("/repo/{owner}/{repo}/contents/{path:path}")
def delete_file(owner: str, repo: str, path: str, request: FileDeleteRequest,
                contents: ContentService = Depends(get_content_service)):
    return run(lambda: contents.delete_file(
        owner, repo, path,
        branch=request.branch,
        message=request.message,
        sha=request.sha,
        confirmed=request.confirmed,
        dry_run=request.dry_run,
    ))
