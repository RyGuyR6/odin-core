from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.github.workflow import GitHubWorkflow


router = APIRouter(
    prefix="/github/workflow",
    tags=["GitHub Workflow"],
)


def get_workflow() -> GitHubWorkflow:
    return GitHubWorkflow()


class ModifyFileRequest(BaseModel):
    owner: str = Field(..., description="GitHub repository owner")
    repo: str = Field(..., description="Repository name")
    branch: str = Field(..., description="Target branch")
    path: str = Field(..., description="File path")
    commit_message: str = Field(..., min_length=1)
    pr_title: str = Field(..., min_length=1)
    pr_body: str = ""


@router.post("/modify-file")
def modify_file(
    request: ModifyFileRequest,
    workflow: Annotated[GitHubWorkflow, Depends(get_workflow)],
):
    """
    Execute a GitHub file modification workflow.
    """

    try:

        result = workflow.modify_file(
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            path=request.path,
            transform=lambda content: content,
            commit_message=request.commit_message,
            pr_title=request.pr_title,
            pr_body=request.pr_body,
        )

        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )